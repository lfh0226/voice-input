"""Tests for the StreamingVoiceInput state machine."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from voice_input.config import Config
from voice_input.main import LOW_LATENCY_FINAL_TIMEOUT, StreamingVoiceInput


class FakeSound:
    def __init__(self, enabled: bool = True) -> None:
        self.errors = 0

    def play_start(self) -> None:
        pass

    def play_end(self) -> None:
        pass

    def play_error(self) -> None:
        self.errors += 1


class FakeRecorder:
    def __init__(self, *args, start_result: bool = True, **kwargs) -> None:
        self.start_calls = 0
        self.stop_calls = 0
        self.start_result = start_result

    def start(self) -> bool:
        self.start_calls += 1
        return self.start_result

    def stop(self) -> None:
        self.stop_calls += 1


class FakeTextInput:
    def __init__(self, *args, **kwargs) -> None:
        self.inputs: list[tuple[str, str | None]] = []

    def input_text(self, text: str, focus_window: str | None = None) -> bool:
        self.inputs.append((text, focus_window))
        return True


class FakeStreamer:
    instances: list["FakeStreamer"] = []

    def __init__(self, *args, **kwargs) -> None:
        self.prepare_calls = 0
        self.start_calls = 0
        self.stop_calls: list[tuple[bool, float]] = []
        self.cleanup_calls = 0
        self.audio_chunks: list[bytes] = []
        self.final_text = "测试文本"
        self.result_text = "测试文本"
        FakeStreamer.instances.append(self)

    def prepare_session(self) -> None:
        self.prepare_calls += 1

    def start(self) -> bool:
        self.start_calls += 1
        return True

    def send_audio(self, pcm_bytes: bytes) -> None:
        self.audio_chunks.append(pcm_bytes)

    def stop(self, close_connection: bool = True, final_result_timeout: float = 8.0) -> str:
        self.stop_calls.append((close_connection, final_result_timeout))
        return self.final_text

    def cleanup(self) -> None:
        self.cleanup_calls += 1


def make_config(tmp_path: Path, reuse_connection: bool = False) -> Config:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "backend: xunfei",
                "xunfei:",
                "  app_id: test_app_id",
                "  api_key: test_api_key",
                "  api_secret: test_api_secret",
                f"  reuse_connection: {str(reuse_connection).lower()}",
                "sound:",
                "  enabled: false",
            ]
        ),
        encoding="utf-8",
    )
    return Config(config_path)


def patch_app_boundaries(monkeypatch) -> None:
    monkeypatch.setattr("voice_input.main.SoundFeedback", FakeSound)
    monkeypatch.setattr("voice_input.main.StreamingRecorder", FakeRecorder)
    monkeypatch.setattr("voice_input.main.TextInput", FakeTextInput)
    monkeypatch.setattr("voice_input.main.XunfeiStreamer", FakeStreamer)
    monkeypatch.setattr(
        "voice_input.main.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout=""),
    )


def test_hotkey_press_starts_recorder_once(monkeypatch, tmp_path: Path) -> None:
    FakeStreamer.instances = []
    patch_app_boundaries(monkeypatch)
    app = StreamingVoiceInput(make_config(tmp_path))

    app._on_hotkey_press()

    streamer = FakeStreamer.instances[0]
    assert streamer.prepare_calls == 1
    assert app.recorder.start_calls == 1
    assert streamer.start_calls == 1
    assert app._is_recording is True


def test_hotkey_release_closes_streamer_by_default(monkeypatch, tmp_path: Path) -> None:
    FakeStreamer.instances = []
    patch_app_boundaries(monkeypatch)
    app = StreamingVoiceInput(make_config(tmp_path))

    app._on_hotkey_press()
    app._on_hotkey_release()

    streamer = FakeStreamer.instances[0]
    assert streamer.stop_calls == [(True, 3.0)]
    assert app.streamer is None
    assert app.text_input.inputs == [("测试文本", None)]


def test_hotkey_release_prefers_latest_callback_text(monkeypatch, tmp_path: Path) -> None:
    FakeStreamer.instances = []
    patch_app_boundaries(monkeypatch)
    app = StreamingVoiceInput(make_config(tmp_path))

    app._on_hotkey_press()
    streamer = FakeStreamer.instances[0]
    streamer.final_text = ""
    app._on_result("本次识别文本", is_final=False)
    app._on_hotkey_release()

    assert streamer.stop_calls == [(True, LOW_LATENCY_FINAL_TIMEOUT)]
    assert app.text_input.inputs == [("本次识别文本", None)]


def test_reuse_connection_keeps_streamer_until_app_stop(monkeypatch, tmp_path: Path) -> None:
    FakeStreamer.instances = []
    patch_app_boundaries(monkeypatch)
    app = StreamingVoiceInput(make_config(tmp_path, reuse_connection=True))
    app._running = True

    app._on_hotkey_press()
    app._on_hotkey_release()

    streamer = FakeStreamer.instances[0]
    assert streamer.stop_calls == [(False, 3.0)]
    assert app.streamer is streamer

    app.stop()
    assert streamer.cleanup_calls == 1
