"""Lightweight local VAD for resident listening.

V2.1 does not add a heavy model dependency.  The first implementation uses an
energy gate with pre-buffer, speech confirmation, hangover and a maximum
segment duration.  It is intentionally synchronous and allocation-free enough
to be called from the PortAudio callback; policy tuning stays behind a small
configuration object.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Callable

import numpy as np


@dataclass(frozen=True)
class VADConfig:
    """Energy VAD policy.

    Durations are converted to frame counts from ``frame_ms``; the default
    80 ms matches the streaming recorder.
    """

    sample_rate: int = 16000
    frame_ms: int = 80
    speech_rms_threshold: float = 500.0
    start_frames: int = 2
    end_silence_ms: int = 700
    min_speech_ms: int = 240
    prebuffer_ms: int = 240
    max_segment_ms: int = 60_000

    def __post_init__(self) -> None:
        if self.sample_rate <= 0 or self.frame_ms <= 0:
            raise ValueError("sample_rate and frame_ms must be positive")
        if self.speech_rms_threshold <= 0:
            raise ValueError("speech_rms_threshold must be positive")
        if self.start_frames < 1:
            raise ValueError("start_frames must be at least 1")
        if self.end_silence_ms <= 0 or self.min_speech_ms <= 0:
            raise ValueError("end_silence_ms and min_speech_ms must be positive")
        if self.prebuffer_ms < 0 or self.max_segment_ms <= 0:
            raise ValueError("prebuffer_ms must be non-negative and max_segment_ms positive")


class EnergyVAD:
    """Split a continuous PCM stream into speech segments.

    Callbacks receive PCM bytes.  ``on_segment_start`` receives the audio
    captured immediately before speech was confirmed, so the first syllable is
    not discarded.  ``on_segment_end`` is emitted after hangover silence.
    """

    def __init__(
        self,
        config: VADConfig | None = None,
        on_segment_start: Callable[[bytes], None] | None = None,
        on_speech: Callable[[bytes], None] | None = None,
        on_segment_end: Callable[[], None] | None = None,
    ) -> None:
        self.config = config or VADConfig()
        self.on_segment_start = on_segment_start
        self.on_speech = on_speech
        self.on_segment_end = on_segment_end

        frame_bytes = int(self.config.sample_rate * 2 * self.config.frame_ms / 1000)
        prebuffer_bytes = int(self.config.sample_rate * 2 * self.config.prebuffer_ms / 1000)
        self._frame_bytes = max(1, frame_bytes)
        self._prebuffer_bytes = max(0, prebuffer_bytes)
        self._end_silence_frames = max(1, self.config.end_silence_ms // self.config.frame_ms)
        self._min_speech_frames = max(1, self.config.min_speech_ms // self.config.frame_ms)
        self._max_segment_frames = max(
            self._min_speech_frames, self.config.max_segment_ms // self.config.frame_ms
        )

        self._prebuffer = deque[bytes]()
        self._prebuffer_size = 0
        self._pending_voiced = 0
        self._speech_frames = 0
        self._silence_frames = 0
        self._segment_frames = 0
        self._is_speaking = False

    @property
    def is_speaking(self) -> bool:
        """Whether a speech segment is currently active."""
        return self._is_speaking

    @staticmethod
    def rms(pcm_bytes: bytes) -> float:
        """Root mean square of little-endian int16 mono PCM."""
        if not pcm_bytes:
            return 0.0
        samples = np.frombuffer(pcm_bytes, dtype="<i2")
        if samples.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(samples.astype(np.float32) ** 2)))

    def _remember(self, pcm_bytes: bytes) -> None:
        if not self._prebuffer_bytes:
            return
        self._prebuffer.append(pcm_bytes)
        self._prebuffer_size += len(pcm_bytes)
        while self._prebuffer_size > self._prebuffer_bytes:
            dropped = self._prebuffer.popleft()
            self._prebuffer_size -= len(dropped)

    def _start_segment(self) -> None:
        self._is_speaking = True
        self._speech_frames = self.config.start_frames
        self._silence_frames = 0
        self._segment_frames = self.config.start_frames
        prebuffer = b"".join(self._prebuffer)
        self._prebuffer.clear()
        self._prebuffer_size = 0
        self._pending_voiced = 0
        if self.on_segment_start:
            self.on_segment_start(prebuffer)

    def _end_segment(self) -> None:
        was_speaking = self._is_speaking
        self._is_speaking = False
        self._speech_frames = 0
        self._silence_frames = 0
        self._segment_frames = 0
        if was_speaking and self.on_segment_end:
            self.on_segment_end()

    def feed(self, pcm_bytes: bytes) -> None:
        """Feed one recorder chunk and invoke segment callbacks."""
        if not pcm_bytes:
            return

        voiced = self.rms(pcm_bytes) >= self.config.speech_rms_threshold
        if not self._is_speaking:
            if voiced:
                self._remember(pcm_bytes)
                self._pending_voiced += 1
                if self._pending_voiced >= self.config.start_frames:
                    self._start_segment()
            else:
                self._pending_voiced = 0
                self._remember(pcm_bytes)
            return

        self._segment_frames += 1
        if voiced:
            self._speech_frames += 1
            self._silence_frames = 0
        else:
            self._silence_frames += 1

        if self.on_speech:
            self.on_speech(pcm_bytes)

        if (
            self._segment_frames >= self._max_segment_frames
            or (
                self._speech_frames >= self._min_speech_frames
                and self._silence_frames >= self._end_silence_frames
            )
        ):
            self._end_segment()

    def flush(self) -> None:
        """End an active segment immediately (used on daemon shutdown)."""
        self._end_segment()
