"""Wyoming protocol handler: one instance per client connection."""

from __future__ import annotations

import logging
import time

from wyoming.audio import AudioChunk, AudioChunkConverter, AudioStart, AudioStop
from wyoming.event import Event
from wyoming.info import Describe, Info
from wyoming.server import AsyncEventHandler
from wyoming.wake import Detect, Detection, NotDetected

from .engine import StreamDetector, WakeModel

_LOGGER = logging.getLogger(__name__)


class MowwEventHandler(AsyncEventHandler):
    def __init__(
        self,
        wyoming_info: Info,
        models: dict[str, WakeModel],
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._wyoming_info = wyoming_info
        self._models = models
        self._converter = AudioChunkConverter(rate=16000, width=2, channels=1)
        self._detectors: dict[str, StreamDetector] = {}
        self._requested: list[str] | None = None
        self._detected = False
        self._chunks = 0
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
            _LOGGER.debug("Audio stream started (models: %s)", ", ".join(names))
            return True

        if AudioChunk.is_type(event.type):
            if self._detected or not self._detectors:
                return True
            self._chunks += 1
            if self._chunks == 1 or self._chunks % 100 == 0:
                _LOGGER.debug(
                    "Audio flowing: chunk %d (~%.1f s)", self._chunks, self._chunks * 0.08
                )
            chunk = self._converter.convert(AudioChunk.from_event(event))
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
            if not self._detected:
                await self.write_event(NotDetected().event())
            _LOGGER.debug(
                "Audio stream stopped (detected=%s, %d chunks)",
                self._detected,
                self._chunks,
            )
            return True

        _LOGGER.debug("Unhandled event type: %s", event.type)
        return True
