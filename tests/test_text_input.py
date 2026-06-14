"""Tests for text input method selection without real desktop input."""

from __future__ import annotations

from types import SimpleNamespace

from voice_input.typer import TextInput


class FakePipe:
    def __init__(self) -> None:
        self.writes: list[str] = []
        self.closed = False

    def write(self, value: str) -> None:
        self.writes.append(value)

    def read(self) -> str:
        return ""

    def close(self) -> None:
        self.closed = True


class FakePopen:
    instances: list["FakePopen"] = []

    def __init__(self, cmd, *args, returncode=None, **kwargs) -> None:
        self.cmd = cmd
        self.returncode = returncode
        self.terminated = False
        self.killed = False
        self.wait_calls = 0
        self.stdin = FakePipe()
        self.stderr = FakePipe()
        FakePopen.instances.append(self)

    def poll(self):
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = 0

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9

    def wait(self, timeout=None):
        self.wait_calls += 1
        return self.returncode


def test_empty_text_returns_false_without_subprocess(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        "voice_input.typer.subprocess.run", lambda *args, **kwargs: calls.append(args)
    )

    assert TextInput(method="clipboard").input_text("") is False
    assert calls == []


def test_clipboard_method_uses_async_wl_copy_stdin_and_ydotool(monkeypatch) -> None:
    FakePopen.instances = []
    commands: list[list[str]] = []

    def fake_which(tool: str) -> str | None:
        return f"/usr/bin/{tool}" if tool in {"wl-copy", "ydotool"} else None

    def fake_run(cmd, *args, **kwargs):
        commands.append(cmd)
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr("voice_input.typer.shutil.which", fake_which)
    monkeypatch.setattr("voice_input.typer.subprocess.Popen", FakePopen)
    monkeypatch.setattr("voice_input.typer.subprocess.run", fake_run)
    monkeypatch.setattr("voice_input.typer.time.sleep", lambda _seconds: None)

    assert TextInput(method="clipboard").input_text("测试") is True

    process = FakePopen.instances[0]
    assert process.cmd[-1] == "wl-copy"
    assert "测试" not in process.cmd
    assert process.stdin.writes == ["测试"]
    assert process.stdin.closed is True
    assert commands == [["ydotool", "key", "29:1", "47:1", "47:0", "29:0"]]


def test_clipboard_method_only_waits_briefly_for_wl_copy_start(monkeypatch) -> None:
    sleeps: list[float] = []

    monkeypatch.setattr(
        "voice_input.typer.shutil.which",
        lambda tool: f"/usr/bin/{tool}" if tool in {"wl-copy", "ydotool"} else None,
    )
    monkeypatch.setattr("voice_input.typer.subprocess.Popen", FakePopen)
    monkeypatch.setattr(
        "voice_input.typer.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stderr=""),
    )
    monkeypatch.setattr("voice_input.typer.time.sleep", lambda seconds: sleeps.append(seconds))

    assert TextInput(method="clipboard").input_text("测试") is True

    assert sleeps == [0.05]


def test_replacing_clipboard_owner_reaps_previous_process(monkeypatch) -> None:
    FakePopen.instances = []
    monkeypatch.setattr(
        "voice_input.typer.shutil.which",
        lambda tool: f"/usr/bin/{tool}" if tool in {"wl-copy", "ydotool"} else None,
    )
    monkeypatch.setattr("voice_input.typer.subprocess.Popen", FakePopen)
    monkeypatch.setattr(
        "voice_input.typer.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stderr=""),
    )
    monkeypatch.setattr("voice_input.typer.time.sleep", lambda _seconds: None)

    text_input = TextInput(method="clipboard")
    assert text_input.input_text("第一次") is True
    first_process = FakePopen.instances[0]

    assert text_input.input_text("第二次") is True

    assert first_process.terminated is True
    assert first_process.wait_calls == 1
    assert first_process.stderr.closed is True
