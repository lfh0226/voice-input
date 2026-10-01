"""Unit tests for V2.1 resident listening building blocks."""

from __future__ import annotations

import time

import numpy as np

from voice_input.resident import ASRSessionRelay
from voice_input.vad import EnergyVAD, VADConfig


def pcm(ms: int, rms: int, sample_rate: int = 16000) -> bytes:
    """Create little-endian int16 mono PCM at an approximate RMS level."""
    samples = int(sample_rate * ms / 1000)
    # A square wave has an RMS equal to its amplitude.
    wave = np.zeros(samples, dtype=np.int16)
    wave[::2] = rms
    wave[1::2] = -rms
    if samples % 2:
        wave[::2] = wave[::2][: wave[::2].size]
    return wave.tobytes()


def test_energy_vad_emits_prebuffer_and_speech_tail() -> None:
    started: list[bytes] = []
    speech: list[bytes] = []
    ended: list[bool] = []
    vad = EnergyVAD(
        VADConfig(start_frames=2, end_silence_ms=160, min_speech_ms=160, prebuffer_ms=160),
        on_segment_start=started.append,
        on_speech=speech.append,
        on_segment_end=lambda: ended.append(True),
    )

    silence = pcm(80, 0)
    loud = pcm(80, 1000)
    for _ in range(2):
        vad.feed(silence)
    vad.feed(loud)  # confirmation frame one
    vad.feed(loud)  # confirmation frame two -> starts with both frames
    vad.feed(loud)
    for _ in range(3):
        vad.feed(silence)

    assert ended == [True]
    assert started == [loud * 2]
    assert speech == [loud, silence, silence]


def test_energy_vad_ignores_too_short_sound() -> None:
    ended: list[bool] = []
    vad = EnergyVAD(
        VADConfig(start_frames=2, min_speech_ms=240, end_silence_ms=80),
        on_segment_end=lambda: ended.append(True),
    )
    silence = pcm(80, 0)
    loud = pcm(80, 900)

    vad.feed(silence)
    vad.feed(loud)
    vad.feed(silence)

    assert vad.is_speaking is False
    assert ended == []


class FakeSession:
    instances: list["FakeSession"] = []
    _session_count = 0

    def __init__(self, start_result: bool = True, start_delay: float = 0.0) -> None:
        self.prepared = False
        self.started = False
        self.cleaned = False
        self.audio: list[bytes] = []
        self.stop_calls: list[tuple[bool, float]] = []
        self.start_result = start_result
        self.start_delay = start_delay
        FakeSession._session_count += 1
        self.final_text = f"final-{FakeSession._session_count}"
        FakeSession.instances.append(self)

    def prepare_session(self) -> None:
        self.prepared = True

    def start(self) -> bool:
        if self.start_delay:
            time.sleep(self.start_delay)
        self.started = self.start_result
        return self.start_result

    def send_audio(self, pcm_bytes: bytes) -> None:
        self.audio.append(pcm_bytes)

    def stop(self, close_connection: bool, final_result_timeout: float) -> str:
        self.stop_calls.append((close_connection, final_result_timeout))
        return self.final_text

    def cleanup(self) -> None:
        self.cleaned = True


def test_relay_warms_session_before_audio() -> None:
    FakeSession.instances = []
    FakeSession._session_count = 0
    finals: list[str] = []
    relay = ASRSessionRelay(
        create_session=FakeSession,
        on_result=lambda text, final: None,
        on_final=finals.append,
        final_result_timeout=0.1,
    )

    relay.warm()
    relay.send_audio(b"first")
    deadline = time.time() + 1
    while time.time() < deadline and not relay.is_ready:
        time.sleep(0.005)

    assert relay.is_ready
    assert FakeSession.instances[0].audio == [b"first"]
    relay.finish_segment()
    relay.stop()
    assert finals == ["final-1"]


def test_relay_warms_next_session_while_previous_finalizes() -> None:
    FakeSession.instances = []
    FakeSession._session_count = 0
    finals: list[str] = []
    relay = ASRSessionRelay(
        create_session=lambda: FakeSession(start_delay=0.02),
        on_result=lambda text, final: None,
        on_final=finals.append,
        final_result_timeout=0.1,
    )

    relay.warm()
    relay.finish_segment()
    assert FakeSession.instances[0].audio == []
    deadline = time.time() + 1
    while time.time() < deadline and len(FakeSession.instances) < 2:
        time.sleep(0.005)

    assert len(FakeSession.instances) == 2
    relay.stop()
    assert finals == ["final-1"]
