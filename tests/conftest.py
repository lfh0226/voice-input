"""Shared pytest fixtures for safe, side-effect-free tests."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def dummy_xunfei_config() -> dict[str, str]:
    """Return non-secret Xunfei credentials for tests."""
    return {
        "app_id": "test_app_id",
        "api_key": "test_api_key",
        "api_secret": "test_api_secret",
    }


@pytest.fixture
def temp_config_path(tmp_path: Path) -> Path:
    """Return a config path isolated from the real project config.yaml."""
    path = tmp_path / "config.yaml"
    path.write_text(
        "\n".join(
            [
                "backend: xunfei",
                "xunfei:",
                "  app_id: test_app_id",
                "  api_key: test_api_key",
                "  api_secret: test_api_secret",
            ]
        ),
        encoding="utf-8",
    )
    return path
