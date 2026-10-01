"""Tests for configuration isolation and entrypoint consistency."""

from __future__ import annotations

from pathlib import Path

from voice_input.config import Config


def test_config_instances_do_not_share_nested_defaults(tmp_path: Path) -> None:
    """Loading one config must not mutate nested defaults used by later instances."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text("input:\n  method: xdotool\n", encoding="utf-8")

    first = Config(config_path)
    assert first.input_config["method"] == "xdotool"

    first.input_config["method"] = "mutated"

    missing_path = tmp_path / "missing.yaml"
    second = Config(missing_path)
    assert second.input_config["method"] == "clipboard"


def test_xunfei_reuse_connection_defaults_to_false(tmp_path: Path) -> None:
    """Connection reuse is opt-in until live API behavior is verified."""
    config = Config(tmp_path / "missing.yaml")
    assert config.xunfei["reuse_connection"] is False


def test_xunfei_final_result_timeout_defaults_to_stable_value(tmp_path: Path) -> None:
    """No-interim-result sessions should wait long enough for the final response."""
    config = Config(tmp_path / "missing.yaml")
    assert config.xunfei["final_result_timeout"] == 3.0


def test_resident_listening_is_opt_in(tmp_path: Path) -> None:
    """Continuous microphone capture must stay disabled until explicitly chosen."""
    config = Config(tmp_path / "missing.yaml")
    assert config.resident["enabled"] is False
    assert config.resident["prebuffer_ms"] > 0


def test_project_exposes_lb_voice_and_legacy_voice_input_scripts() -> None:
    """The shell launcher can rely on lb-voice while legacy voice-input remains available."""
    pyproject = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    assert 'lb-voice = "voice_input.run:main"' in pyproject
    assert 'voice-input = "voice_input.run:main"' in pyproject
