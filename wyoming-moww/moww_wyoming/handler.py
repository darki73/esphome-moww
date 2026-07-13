"""Wyoming protocol handler: one instance per client connection."""

from __future__ import annotations

import logging
import time
import wave
from datetime import datetime
from pathlib import Path

from wyoming.audio import AudioChunk, AudioChunkConverter, AudioStart, AudioStop
from wyoming.event import Event
from wyoming.info import Describe, Info
from wyoming.server import AsyncEventHandler
from wyoming.wake import Detect, Detection, NotDetected

from .engine import StreamDetector, WakeModel

_LOGGER = logging.getLogger(__name__)


class MowwEventHandler(AsyncEventHandler):
    # Cap for save_audio session dumps; HA closes wake sessions after ~6 s,
    # so the threshold must sit below that or nothing ever flushes
    _SAVE_SECONDS = 6

    def __init__(
        self,
        wyoming_info: Info,
        models: dict[str, WakeModel],
        save_dir: Path | None,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._wyoming_info = wyoming_info
        self._models = models
        self._save_dir = save_dir
        self._save_buffer = bytearray()
        self._save_written = False
        self._converter = AudioChunkConverter(rate=16000, width=2, channels=1)
        self._detectors: dict[str, StreamDetector] = {}
        self._requested: list[str] | None = None
        self._detected = False
        self._chunks = 0
        self._audio_bytes = 0
        _LOGGER.debug("Client connected")

    async def handle_event(self, event: Event) -> bool:
        if Describe.is_type(event.type):
            await self.write_event(self._wyoming_info.event())
            return True

        if Detect.is_type(event.type):
            detect = Detect.from_event(event)
            if detect.names:
                self._requested = [
                    name for name in detect.names if name in self._models
                ]
                unknown = set(detect.names) - set(self._models)
                if unknown:
                    _LOGGER.warning("Requested unknown wake word(s): %s", unknown)
            return True

        if AudioStart.is_type(event.type):
            names = self._requested or list(self._models)
            self._detectors = {
                name: StreamDetector(self._models[name]) for name in names
            }
            self._detected = False
            self._chunks = 0
            self._audio_bytes = 0
            self._save_buffer.clear()
            self._save_written = False
            _LOGGER.debug("Audio stream started (models: %s)", ", ".join(names))
            return True

        if AudioChunk.is_type(event.type):
            if self._detected or not self._detectors:
                return True
            self._chunks += 1
            chunk = self._converter.convert(AudioChunk.from_event(event))
            self._audio_bytes += len(chunk.audio)
            if self._chunks == 1 or self._chunks % 100 == 0:
                _LOGGER.debug(
                    "Audio flowing: chunk %d (%.2f s of audio)",
                    self._chunks,
                    self._audio_bytes / 32000.0,
                )
            self._maybe_save_(chunk.audio)
            start = time.monotonic()
            for name, detector in self._detectors.items():
                detection = detector.process(chunk.audio)
                if detection is None:
                    continue
                self._detected = True
                _LOGGER.info(
                    "Detected '%s' at %d ms (stage1 %.2f, verifier %s) in %.0f ms",
                    name,
                    detection.timestamp_ms,
                    detection.stage1_probability,
                    f"{detection.verifier_score:.2f}"
                    if detection.verifier_score is not None
                    else "off",
                    (time.monotonic() - start) * 1000,
                )
                await self.write_event(
                    Detection(
                        name=name, timestamp=detection.timestamp_ms
                    ).event()
                )
                break
            return True

        if AudioStop.is_type(event.type):
            self._flush_save_()
            if not self._detected:
                await self.write_event(NotDetected().event())
            _LOGGER.debug(
                "Audio stream stopped (detected=%s, %d chunks, %.2f s)",
                self._detected,
                self._chunks,
                self._audio_bytes / 32000.0,
            )
            return True

        _LOGGER.debug("Unhandled event type: %s", event.type)
        return True

    def _maybe_save_(self, audio: bytes) -> None:
        """Dump the first _SAVE_SECONDS of a session to a WAV for analysis."""
        if self._save_dir is None or self._save_written:
            return
        self._save_buffer.extend(audio)
        if len(self._save_buffer) >= 16000 * 2 * self._SAVE_SECONDS:
            self._flush_save_()

    def _flush_save_(self) -> None:
        """Write whatever session audio is buffered (also called at stream end)."""
        if (
            self._save_dir is None
            or self._save_written
            or len(self._save_buffer) < 16000  # not worth keeping under 0.5 s
        ):
            return
        self._save_written = True
        self._save_dir.mkdir(parents=True, exist_ok=True)
        path = self._save_dir / (
            datetime.now().strftime("session_%Y%m%d_%H%M%S.wav")
        )
        with wave.open(str(path), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(16000)
            out.writeframes(bytes(self._save_buffer))
        self._save_buffer.clear()
        _LOGGER.info("Saved session audio to %s", path)
