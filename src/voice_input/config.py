"""Configuration management module."""

import copy
import os
from pathlib import Path
from typing import Any

import yaml


class Config:
    """Configuration manager for voice input."""

    DEFAULT_CONFIG = {
        "backend": "xunfei",
        "hotkey": {
            "trigger": "alt",
            "mode": "hold",
        },
        "recording": {
            "sample_rate": 16000,
            "channels": 1,
            "chunk_ms": 40,
            "max_duration": 30,
        },
        "xunfei": {
            "app_id": "",
            "api_key": "",
            "api_secret": "",
            "language": "zh_cn",
            "accent": "mandarin",
            "max_audio_queue_size": 400,
            "batch_chunks": 2,
            "reuse_connection": False,
            "final_result_timeout": 3.0,
        },
        "tencent": {
            "app_id": "",
            "secret_id": "",
            "secret_key": "",
        },
        "baidu": {
            "app_id": "",
            "api_key": "",
            "secret_key": "",
        },
        "sound": {
            "enabled": True,
        },
        "notification": {
            "enabled": False,
            "show_status": False,
            "show_result": False,
        },
        "input": {
            "method": "clipboard",
            "type_delay": 0.005,
        },
        "logging": {
            "level": "info",  # debug, info, warning, error
            "show_audio_chunks": False,  # 是否打印音频块处理信息
            "show_recognized_text": False,  # 是否打印识别的文本内容
        },
    }

    def __init__(self, config_path: Path | None = None):
        """Initialize configuration.

        Args:
            config_path: Path to config file. If None, uses default locations.
        """
        self._config: dict[str, Any] = {}
        self._config_path = config_path or self._find_config_path()
        self._load_config()

    def _find_config_path(self) -> Path:
        """Find configuration file in standard locations."""
        # Priority: XDG config home > project dir > home
        locations = [
            Path(os.environ.get("XDG_CONFIG_HOME", "~/.config")).expanduser()
            / "voice-input"
            / "config.yaml",
            Path.home() / ".voice-input" / "config.yaml",
            Path(__file__).parent.parent.parent / "config.yaml",
        ]

        for loc in locations:
            if loc.exists():
                return loc

        # Return default location for creating new config
        return locations[0]

    def _load_config(self) -> None:
        """Load configuration from file."""
        # Start with defaults
        self._config = copy.deepcopy(self.DEFAULT_CONFIG)

        # Deep merge with file config
        if self._config_path.exists():
            with open(self._config_path, "r", encoding="utf-8") as f:
                file_config = yaml.safe_load(f) or {}
                self._deep_merge(self._config, file_config)

    def _deep_merge(self, base: dict, override: dict) -> None:
        """Deep merge override dict into base dict."""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by dot-separated key.

        Args:
            key: Dot-separated key path (e.g., "whisper.model")
            default: Default value if key not found

        Returns:
            Configuration value or default.
        """
        keys = key.split(".")
        value = self._config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    def __getitem__(self, key: str) -> Any:
        """Get configuration value."""
        return self._config[key]

    @property
    def backend(self) -> str:
        """Current speech recognition backend."""
        return self._config["backend"]

    @property
    def hotkey(self) -> dict:
        """Hotkey configuration."""
        return self._config["hotkey"]

    @property
    def recording(self) -> dict:
        """Recording configuration."""
        return self._config["recording"]

    @property
    def xunfei(self) -> dict:
        """Xunfei configuration."""
        return self._config["xunfei"]

    @property
    def tencent(self) -> dict:
        """Tencent configuration."""
        return self._config["tencent"]

    @property
    def baidu(self) -> dict:
        """Baidu configuration."""
        return self._config["baidu"]

    @property
    def sound(self) -> dict:
        """Sound configuration."""
        return self._config["sound"]

    @property
    def notification(self) -> dict:
        """Notification configuration."""
        return self._config["notification"]

    @property
    def input_config(self) -> dict:
        """Input configuration."""
        return self._config["input"]

    @property
    def logging_config(self) -> dict:
        """Logging configuration."""
        return self._config.get(
            "logging",
            {
                "level": "info",
                "show_audio_chunks": False,
                "show_recognized_text": False,
            },
        )

    def save(self) -> None:
        """Save current configuration to file."""
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        self._config_path.parent.chmod(0o700)
        with open(self._config_path, "w", encoding="utf-8") as f:
            yaml.dump(self._config, f, default_flow_style=False, allow_unicode=True)
        self._config_path.chmod(0o600)


# Global config instance
_config: Config | None = None


def get_config(config_path: Path | None = None) -> Config:
    """Get global configuration instance."""
    global _config
    if _config is None:
        _config = Config(config_path)
    return _config
