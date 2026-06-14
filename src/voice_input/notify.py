"""System notification module."""

import logging
import subprocess
import sys

logger = logging.getLogger(__name__)


class Notifier:
    """Cross-platform system notification handler."""

    def __init__(self, enabled: bool = True):
        """Initialize notifier.

        Args:
            enabled: Whether notifications are enabled.
        """
        self.enabled = enabled
        self._method = self._detect_method()

    def _detect_method(self) -> str | None:
        """Detect available notification method.

        Returns:
            Method name or None if no method available.
        """
        # Check for notify-send (Linux)
        try:
            result = subprocess.run(
                ["which", "notify-send"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return "notify-send"
        except Exception:
            pass

        # Check for zenity (Linux fallback)
        try:
            result = subprocess.run(
                ["which", "zenity"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return "zenity"
        except Exception:
            pass

        # Check for platform-specific methods
        if sys.platform == "darwin":
            try:
                result = subprocess.run(
                    ["which", "osascript"],
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    return "osascript"
            except Exception:
                pass

        logger.warning("No notification method found")
        return None

    def notify(
        self,
        title: str,
        message: str = "",
        timeout: int = 3000,
    ) -> bool:
        """Show a system notification.

        Args:
            title: Notification title.
            message: Notification message.
            timeout: Notification timeout in milliseconds.

        Returns:
            True if notification was shown successfully.
        """
        if not self.enabled or not self._method:
            return False

        try:
            if self._method == "notify-send":
                cmd = [
                    "notify-send",
                    "-t",
                    str(timeout),
                    "-a",
                    "Voice Input",
                    title,
                ]
                if message:
                    cmd.append(message)
                subprocess.run(cmd, check=True)
                return True

            elif self._method == "zenity":
                cmd = [
                    "zenity",
                    "--notification",
                    f"--text={title}: {message}" if message else f"--text={title}",
                ]
                subprocess.run(cmd, check=True)
                return True

            elif self._method == "osascript":
                script = f'display notification "{message}" with title "{title}"'
                subprocess.run(["osascript", "-e", script], check=True)
                return True

        except Exception as e:
            logger.error(f"Failed to show notification: {e}")
            return False

        return False

    def notify_recording_start(self) -> None:
        """Show notification that recording has started."""
        self.notify("🎤 Voice Input", "Recording... Speak now")

    def notify_recording_stop(self) -> None:
        """Show notification that recording has stopped."""
        self.notify("🎤 Voice Input", "Processing...")

    def notify_result(self, text: str) -> None:
        """Show notification with recognition result.

        Args:
            text: Recognized text.
        """
        # Truncate long text
        display_text = text[:100] + "..." if len(text) > 100 else text
        self.notify("🎤 Recognized", display_text)

    def notify_error(self, error: str) -> None:
        """Show error notification.

        Args:
            error: Error message.
        """
        self.notify("❌ Voice Input Error", error)
