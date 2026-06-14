"""Tests for streaming recorder behavior without opening audio devices."""

from __future__ import annotations

import numpy as np

from voice_input.recorder import StreamingRecorder


class FakeInputStream:
    instances: list["FakeInputStream"] = []

    def __init__(self, *args, **kwargs) -> None:
        self.start_calls = 0
        self.stop_calls = 0
        self.close_calls = 0
        FakeInputStream.instances.append(self)

    def start(self) -> None:
        self.start_calls += 1

    def stop(self) -> None:
        self.stop_calls += 1

    def close(self) -> None:
        self.close_calls += 1


def test_streaming_recorder_rejects_duplicate_start(monkeypatch) -> None:
    FakeInputStream.instances = []
    monkeypatch.setattr("voice_input.recorder.sd.InputStream", FakeInputStream)
    recorder = StreamingRecorder()

    assert recorder.start() is True
    assert recorder.start() is False

    assert len(FakeInputStream.instances) == 1


def test_streaming_recorder_callback_emits_pcm_bytes() -> None:
    chunks: list[bytes] = []
    recorder = StreamingRecorder(on_chunk=chunks.append)
    recorder._is_recording = True
    audio = np.array([[0.0], [1.0], [-1.0]], dtype=np.float32)

    recorder._audio_callback(audio, frames=3, time_info={}, status=None)

    assert chunks == [(audio[:, 0] * 32767).astype(np.int16).tobytes()]
