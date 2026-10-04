"""Hotkey listener module with Wayland support via evdev."""

import logging
import select
import threading
import time
from typing import Callable

logger = logging.getLogger(__name__)

HOTKEY_POLL_TIMEOUT = 0.1
DEVICE_RESCAN_INTERVAL = 5.0  # seconds between device re-scans

# Try to import evdev for Wayland/native Linux support
try:
    import evdev
    from evdev import InputDevice, categorize, ecodes

    EVDEV_AVAILABLE = True
except ImportError:
    EVDEV_AVAILABLE = False


class HotkeyListener:
    """Global hotkey listener using evdev for Linux/Wayland support."""

    # Key name to evdev code mapping
    KEY_MAP = {
        "alt": ecodes.KEY_LEFTALT,
        "alt_l": ecodes.KEY_LEFTALT,
        "alt_r": ecodes.KEY_RIGHTALT,
        "ctrl": ecodes.KEY_LEFTCTRL,
        "ctrl_l": ecodes.KEY_LEFTCTRL,
        "ctrl_r": ecodes.KEY_RIGHTCTRL,
        "shift": ecodes.KEY_LEFTSHIFT,
        "shift_l": ecodes.KEY_LEFTSHIFT,
        "shift_r": ecodes.KEY_RIGHTSHIFT,
        "super": ecodes.KEY_LEFTMETA,
        "cmd": ecodes.KEY_LEFTMETA,
        "win": ecodes.KEY_LEFTMETA,
        "meta": ecodes.KEY_LEFTMETA,
    }

    # Alias mapping: alias -> list of key codes
    KEY_ALIASES = {
        "alt": [ecodes.KEY_LEFTALT, ecodes.KEY_RIGHTALT],
        "ctrl": [ecodes.KEY_LEFTCTRL, ecodes.KEY_RIGHTCTRL],
        "shift": [ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT],
    }

    def __init__(
        self,
        hotkey: str,
        on_press: Callable[[], None],
        on_release: Callable[[], None] | None = None,
        mode: str = "hold",
    ):
        """Initialize hotkey listener.

        Args:
            hotkey: Hotkey combination string (e.g., "alt", "ctrl+alt+v").
            on_press: Callback when hotkey is pressed.
            on_release: Callback when hotkey is released (hold mode only).
            mode: "hold" or "toggle".
        """
        self.hotkey_str = hotkey
        self.on_press = on_press
        self.on_release = on_release
        self.mode = mode

        self._is_active = False
        self._toggle_state = False
        self._running = False
        self._thread: threading.Thread | None = None
        self._pressed_keys: set[int] = set()
        self._hotkey_codes: list[int | list[int]] = []
        self._devices: list[InputDevice] = []
        self._last_rescan: float = 0.0

        self._parse_hotkey()

    def _parse_hotkey(self) -> None:
        """Parse hotkey string into evdev key codes."""
        parts = self.hotkey_str.lower().split("+")

        for part in parts:
            part = part.strip()
            if part in self.KEY_ALIASES:
                # Store as list of codes for alias matching
                self._hotkey_codes.append(self.KEY_ALIASES[part])
            elif part in self.KEY_MAP:
                self._hotkey_codes.append(self.KEY_MAP[part])
            elif len(part) == 1:
                # Single character key
                code = getattr(ecodes, f"KEY_{part.upper()}", None)
                if code:
                    self._hotkey_codes.append(code)
                else:
                    logger.warning(f"Unknown key: {part}")
            else:
                # Try KEY_NAME format
                code = getattr(ecodes, f"KEY_{part.upper()}", None)
                if code:
                    self._hotkey_codes.append(code)
                else:
                    logger.warning(f"Unknown key: {part}")

        logger.info(f"Parsed hotkey '{self.hotkey_str}' -> codes: {self._hotkey_codes}")

    def _check_hotkey_pressed(self) -> bool:
        """Check if all hotkey keys are currently pressed."""
        for code in self._hotkey_codes:
            if isinstance(code, list):
                # Alias: any of the codes must be pressed
                if not any(c in self._pressed_keys for c in code):
                    return False
            elif code not in self._pressed_keys:
                return False
        return True

    def _is_hotkey_key(self, code: int) -> bool:
        """Check if a key code is part of our hotkey."""
        for hc in self._hotkey_codes:
            if isinstance(hc, list):
                if code in hc:
                    return True
            elif hc == code:
                return True
        return False

    def _handle_event(self, event) -> None:
        """Handle a keyboard event."""
        if event.type != ecodes.EV_KEY:
            return

        key_event = categorize(event)
        code = key_event.event.code

        if key_event.keystate == 1:  # Key press
            self._pressed_keys.add(code)

            if self._check_hotkey_pressed():
                if self.mode == "hold":
                    if not self._is_active:
                        self._is_active = True
                        logger.info("Hotkey pressed - starting recording")
                        if self.on_press:
                            self.on_press()
                elif self.mode == "toggle":
                    self._toggle_state = not self._toggle_state
                    logger.info(f"Hotkey toggled: {self._toggle_state}")
                    if self._toggle_state and self.on_press:
                        self.on_press()
                    elif not self._toggle_state and self.on_release:
                        self.on_release()

        elif key_event.keystate == 0:  # Key release
            self._pressed_keys.discard(code)

            if self.mode == "hold" and self._is_active:
                if self._is_hotkey_key(code):
                    self._is_active = False
                    logger.info("Hotkey released - stopping recording")
                    if self.on_release:
                        self.on_release()

    def _find_keyboard_devices(self) -> list[InputDevice]:
        """Find all keyboard input devices."""
        devices = []

        for path in evdev.list_devices():
            try:
                dev = InputDevice(path)
                capabilities = dev.capabilities()

                # Check if device has keyboard keys
                if ecodes.EV_KEY in capabilities:
                    keys = capabilities[ecodes.EV_KEY]
                    # Check for common keyboard indicators: ALT key or letter keys
                    has_alt = ecodes.KEY_LEFTALT in keys or ecodes.KEY_RIGHTALT in keys
                    has_letters = ecodes.KEY_A in keys and ecodes.KEY_Z in keys
                    if has_alt or has_letters:
                        logger.info(f"Found keyboard device: {dev.name} ({path})")
                        devices.append(dev)
                    else:
                        logger.debug(f"Skipped non-keyboard device: {dev.name} ({path})")
            except Exception as e:
                logger.debug(f"Could not open device {path}: {e}")
                continue

        return devices

    def _rescan_devices(self) -> None:
        """Re-scan for newly connected keyboard devices (e.g. Bluetooth)."""
        try:
            current_paths = {dev.path for dev in self._devices}
            new_devices = self._find_keyboard_devices()
            for dev in new_devices:
                if dev.path not in current_paths:
                    logger.info(f"New keyboard device discovered: {dev.name} ({dev.path})")
                    self._devices.append(dev)
        except Exception as e:
            logger.debug(f"Device re-scan failed: {e}")

    def _run(self) -> None:
        """Main event loop."""
        if not EVDEV_AVAILABLE:
            logger.error("evdev not available, cannot listen for hotkeys")
            return

        self._devices = self._find_keyboard_devices()

        if not self._devices:
            logger.error("No keyboard devices found!")
            return

        logger.info(f"Monitoring {len(self._devices)} keyboard device(s)")

        while self._running:
            try:
                readable_devices, _, _ = select.select(self._devices, [], [], HOTKEY_POLL_TIMEOUT)

                for dev in readable_devices:
                    try:
                        for event in dev.read():
                            if not self._running:
                                break
                            self._handle_event(event)
                    except BlockingIOError:
                        continue
                    except Exception as e:
                        logger.debug(f"Error reading from {dev.name}: {e}")

                # 定期重新扫描新连接的键盘设备（蓝牙键盘可能晚于服务启动）
                now = time.monotonic()
                if now - self._last_rescan >= DEVICE_RESCAN_INTERVAL:
                    self._rescan_devices()
                    self._last_rescan = now

            except Exception as e:
                logger.error(f"Error in event loop: {e}")
                break

    def start(self) -> None:
        """Start listening for hotkey."""
        if self._running:
            return

        if not EVDEV_AVAILABLE:
            logger.error("evdev not available. Install with: pip install evdev")
            return

        logger.info(f"Starting hotkey listener: {self.hotkey_str} (mode: {self.mode})")
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop listening for hotkey."""
        if not self._running:
            return

        logger.info("Stopping hotkey listener")
        self._running = False

        # Close devices
        for dev in self._devices:
            try:
                dev.close()
            except Exception:
                pass
        self._devices.clear()

        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None

    def is_active(self) -> bool:
        """Check if hotkey is currently active."""
        return self._is_active or self._toggle_state

    def __enter__(self) -> "HotkeyListener":
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.stop()
