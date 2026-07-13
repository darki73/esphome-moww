"""The moww cascade, server-side: streaming v2 detector + one-shot verifier.

Mirrors the ESPHome component's semantics so a detection here means the
same thing it means on-device:

- stage 1: contract-v2 streaming model at a recall-greedy cutoff,
  5-wide sliding mean over the probability stream;
- stage 2: non-streaming verifier re-scores the last ~2 s of features at
  several delays after the stage-1 candidate (the candidate fires mid-word;
  the verifier only scores well once the whole word is in the window).
"""

from __future__ import annotations

import json
import logging
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .frontend import FEATURE_SIZE, STEP_MS, StreamingFrontend

_LOGGER = logging.getLogger(__name__)

SLIDING_WINDOW = 5
# Deferred verification scan band, in 10 ms feature frames after the
# stage-1 candidate (same values as the firmware).
VERIFY_FIRST_FRAMES = 10
VERIFY_LAST_FRAMES = 50
VERIFY_STRIDE_FRAMES = 5
# Frames to suppress new candidates after a resolved one.
REFRACTORY_AFTER_DETECT = 100
REFRACTORY_AFTER_REFUTE = 25


class StreamingModel:
    """Contract-v2 streaming TFLite: explicit state tensors, fed back."""

    def __init__(self, path: Path) -> None:
        from ai_edge_litert.interpreter import Interpreter

        self._interpreter = Interpreter(model_path=str(path))
        self._runner = self._interpreter.get_signature_runner()
        inputs = self._runner.get_input_details()
        outputs = self._runner.get_output_details()

        self._state_names = sorted(n for n in inputs if n.startswith("state_"))
        self._data_name = next(n for n in inputs if not n.startswith("state_"))
        ordered = sorted(outputs, key=lambda n: int(n.rsplit("_", 1)[1]))
        self._prob_name = ordered[0]
        self._state_outputs = ordered[1:]

        detail = inputs[self._data_name]
        self.chunk_frames = int(detail["shape"][1])
        # Float exports carry no quantization params (dev builds); int8 is
        # what actually ships
        self._quantized = np.dtype(detail["dtype"]) == np.int8
        if self._quantized:
            params = detail["quantization_parameters"]
            self._in_scale = float(params["scales"][0])
            self._in_zero = int(params["zero_points"][0])
            out_params = outputs[self._prob_name]["quantization_parameters"]
            self._out_scale = float(out_params["scales"][0])
            self._out_zero = int(out_params["zero_points"][0])
        self._initial_states = {
            name: (
                np.full(
                    inputs[name]["shape"],
                    inputs[name]["quantization_parameters"]["zero_points"][0],
                    dtype=np.int8,
                )
                if self._quantized
                else np.zeros(inputs[name]["shape"], dtype=np.float32)
            )
            for name in self._state_names
        }

    def initial_states(self) -> dict[str, np.ndarray]:
        return dict(self._initial_states)

    def step(
        self, frames: np.ndarray, states: dict[str, np.ndarray]
    ) -> tuple[float, dict[str, np.ndarray]]:
        chunk = frames[None].astype(np.float32)
        if self._quantized:
            chunk = np.clip(
                np.round(chunk / self._in_scale + self._in_zero), -128, 127
            ).astype(np.int8)
        feed = {self._data_name: chunk}
        feed.update(states)
        result = self._runner(**feed)
        raw = float(np.asarray(result[self._prob_name]).ravel()[0])
        probability = (
            (raw - self._out_zero) * self._out_scale if self._quantized else raw
        )
        next_states = {
            state: result[out]
            for out, state in zip(self._state_outputs, self._state_names)
        }
        return probability, next_states


class VerifierModel:
    """Non-streaming one-shot verifier over a fixed feature window."""

    def __init__(self, path: Path) -> None:
        from ai_edge_litert.interpreter import Interpreter

        self._interpreter = Interpreter(model_path=str(path))
        self._interpreter.allocate_tensors()
        detail = self._interpreter.get_input_details()[0]
        self._input_index = detail["index"]
        self.window_frames = int(detail["shape"][1])
        params = detail["quantization_parameters"]
        self._in_scale = float(params["scales"][0])
        self._in_zero = int(params["zero_points"][0])
        out = self._interpreter.get_output_details()[0]
        self._output_index = out["index"]
        self._out_unsigned = np.dtype(out["dtype"]) == np.uint8

    def score(self, window: np.ndarray) -> float:
        quantized = np.clip(
            np.round(window[None] / self._in_scale + self._in_zero), -128, 127
        ).astype(np.int8)
        self._interpreter.set_tensor(self._input_index, quantized)
        self._interpreter.invoke()
        raw = int(self._interpreter.get_tensor(self._output_index).ravel()[0])
        if not self._out_unsigned:
            raw += 128
        return raw / 255.0


@dataclass(frozen=True)
class WakeModel:
    """One wake word: model files plus resolved cutoffs."""

    name: str
    phrase: str
    streaming: StreamingModel
    verifier: VerifierModel | None
    stage1_cutoff: float
    verifier_cutoff: float

    @staticmethod
    def load(
        streaming_path: Path,
        verifier_path: Path | None,
        stage1_cutoff: float,
        verifier_cutoff: float,
    ) -> "WakeModel":
        name = streaming_path.stem
        phrase = name
        manifest = streaming_path.with_suffix(".json")
        if manifest.is_file():
            try:
                raw = json.loads(manifest.read_text(encoding="utf-8"))
                phrase = raw.get("wake_word", name)
            except (OSError, ValueError):
                _LOGGER.warning("Unreadable manifest %s; using file stem", manifest)
        verifier = VerifierModel(verifier_path) if verifier_path else None
        _LOGGER.info(
            "Loaded '%s' (phrase '%s'): stage1 cutoff %.2f, verifier %s",
            name,
            phrase,
            stage1_cutoff,
            f"cutoff {verifier_cutoff:.2f}" if verifier else "disabled",
        )
        return WakeModel(
            name=name,
            phrase=phrase,
            streaming=StreamingModel(streaming_path),
            verifier=verifier,
            stage1_cutoff=stage1_cutoff,
            verifier_cutoff=verifier_cutoff,
        )


@dataclass
class Detection:
    name: str
    timestamp_ms: int
    stage1_probability: float
    verifier_score: float | None


class StreamDetector:
    """Per-connection detector state for one wake model."""

    def __init__(self, model: WakeModel) -> None:
        self._model = model
        self._frontend = StreamingFrontend()
        history = (model.verifier.window_frames if model.verifier else 0) + (
            VERIFY_LAST_FRAMES + SLIDING_WINDOW
        )
        self._history: deque[np.ndarray] = deque(maxlen=max(history, 8))
        self._chunk: list[np.ndarray] = []
        self._states = model.streaming.initial_states()
        self._window: deque[float] = deque(maxlen=SLIDING_WINDOW)
        self._samples = 0
        self._refractory = 0
        self._pending = False
        self._frames_waited = 0
        self._best_score = 0.0
        self._candidate_probability = 0.0

    def process(self, pcm: bytes) -> Detection | None:
        """Feed PCM; returns a Detection when the cascade confirms."""
        self._samples += len(pcm) // 2
        for frame in self._frontend.process(pcm):
            self._history.append(frame)
            detection = self._tick_pending_(frame)
            if detection is not None:
                return detection
            self._chunk.append(frame)
            if len(self._chunk) < self._model.streaming.chunk_frames:
                continue
            frames = np.stack(self._chunk)
            self._chunk.clear()
            probability, self._states = self._model.streaming.step(
                frames, self._states
            )
            self._window.append(probability)
            if self._refractory > 0:
                self._refractory -= 1
                continue
            if self._pending or len(self._window) < SLIDING_WINDOW:
                continue
            mean = sum(self._window) / len(self._window)
            if mean < self._model.stage1_cutoff:
                continue
            self._candidate_probability = mean
            _LOGGER.debug(
                "Stage-1 candidate '%s' (mean %.2f) at %d ms",
                self._model.name,
                mean,
                self._timestamp_ms_(),
            )
            if self._model.verifier is None:
                self._refractory = REFRACTORY_AFTER_DETECT
                self._window.clear()
                return Detection(
                    self._model.name, self._timestamp_ms_(), mean, None
                )
            self._pending = True
            self._frames_waited = 0
            self._best_score = 0.0
            self._window.clear()
        return None

    def _tick_pending_(self, _frame: np.ndarray) -> Detection | None:
        if not self._pending:
            return None
        self._frames_waited += 1
        if (
            self._frames_waited < VERIFY_FIRST_FRAMES
            or self._frames_waited % VERIFY_STRIDE_FRAMES != 0
        ):
            return None
        score = self._model.verifier.score(self._verifier_window_())
        self._best_score = max(self._best_score, score)
        if score >= self._model.verifier_cutoff:
            _LOGGER.debug(
                "Verifier confirmed '%s': score %.2f, +%d ms after candidate",
                self._model.name,
                score,
                self._frames_waited * STEP_MS,
            )
            self._pending = False
            self._refractory = REFRACTORY_AFTER_DETECT
            return Detection(
                self._model.name,
                self._timestamp_ms_(),
                self._candidate_probability,
                score,
            )
        if self._frames_waited >= VERIFY_LAST_FRAMES:
            _LOGGER.debug(
                "Verifier refuted '%s': best score %.2f across delays",
                self._model.name,
                self._best_score,
            )
            self._pending = False
            self._refractory = REFRACTORY_AFTER_REFUTE
        return None

    def _verifier_window_(self) -> np.ndarray:
        window_frames = self._model.verifier.window_frames
        frames = list(self._history)[-window_frames:]
        window = np.zeros((window_frames, FEATURE_SIZE), dtype=np.float32)
        if frames:
            window[-len(frames) :] = np.stack(frames)
        return window

    def _timestamp_ms_(self) -> int:
        return self._samples // 16
