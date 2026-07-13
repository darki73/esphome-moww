"""Incremental micro-frontend: the same C feature generator the ESP32 runs.

pymicro-features wraps the TFLM microfrontend (30 ms window / 10 ms step,
40 mel bins), so features here are bit-compatible with the device's.
"""

from __future__ import annotations

import numpy as np
from pymicro_features import MicroFrontend

SAMPLES_PER_STEP = 160  # 10 ms @ 16 kHz
BYTES_PER_STEP = SAMPLES_PER_STEP * 2
FEATURE_SIZE = 40
STEP_MS = 10


class StreamingFrontend:
    """Feeds arbitrary-sized int16 PCM chunks, yields (40,) float32 frames."""

    def __init__(self) -> None:
        self._frontend = MicroFrontend()
        self._pending = b""

    def process(self, pcm: bytes) -> list[np.ndarray]:
        self._pending += pcm
        frames: list[np.ndarray] = []
        index = 0
        while index + BYTES_PER_STEP <= len(self._pending):
            result = self._frontend.process_samples(
                self._pending[index : index + BYTES_PER_STEP]
            )
            index += result.samples_read * 2
            if result.features:
                frames.append(np.asarray(result.features, dtype=np.float32))
        self._pending = self._pending[index:]
        return frames
