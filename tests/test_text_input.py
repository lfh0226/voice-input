"""Tests for text input method selection without real desktop input."""

from __future__ import annotations

from types import SimpleNamespace

from voice_input.typer import TextInput


def test_empty_text_returns_false_without_subprocess(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        "voice_input.typer.subprocess.run", lambda *args, **kwargs: calls.append(args)
    )

    assert TextInput(method="clipboard").input_text("") is False
    assert calls == []


def test_clipboard_method_uses_wl_copy_and_ydotool_when_available(monkeypatch) -> None:
    commands: list[list[str]] = []

    def fake_which(tool: str) -> str | None:
        return f"/usr/bin/{tool}" if tool in {"wl-copy", "ydotool"} else None

    def fake_run(cmd, *args, **kwargs):
        commands.append(cmd)
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr("voice_input.typer.shutil.which", fake_which)
    monkeypatch.setattr("voice_input.typer.subprocess.run", fake_run)

    assert TextInput(method="clipboard").input_text("测试") is True

    assert commands[0][-3:] == ["wl-copy", "--", "测试"]
    assert commands[1] == ["ydotool", "key", "ctrl+v"]


def test_clipboard_method_waits_briefly_before_pasting(monkeypatch) -> None:
    sleeps: list[float] = []

    monkeypatch.setattr(
        "voice_input.typer.shutil.which",
        lambda tool: f"/usr/bin/{tool}" if tool in {"wl-copy", "ydotool"} else None,
    )
    monkeypatch.setattr(
        "voice_input.typer.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stderr=""),
    )
    monkeypatch.setattr("voice_input.typer.time.sleep", lambda seconds: sleeps.append(seconds))

    assert TextInput(method="clipboard").input_text("测试") is True

    assert sleeps == [0.15]
