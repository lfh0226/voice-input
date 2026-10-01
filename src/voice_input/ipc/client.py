"""向 fcitx5 voiceim 插件推送流式识别结果的 Unix socket 客户端."""

import json
import logging
import os
import socket
import threading

logger = logging.getLogger(__name__)


def _socket_path() -> str:
    runtime = os.environ.get("XDG_RUNTIME_DIR", "/run/user/1000")
    return os.path.join(runtime, "voice-input", "im.sock")


class VoiceIMClient:
    """与 fcitx5 插件保持长连接,断线自动重连."""

    def __init__(self):
        self._sock: socket.socket | None = None
        self._lock = threading.Lock()

    def _connect(self) -> None:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(_socket_path())
        self._sock = s

    def _send(self, payload: dict) -> bool:
        data = (json.dumps(payload) + "\n").encode("utf-8")
        with self._lock:
            for _ in range(2):  # 一次失败重连重试
                try:
                    if self._sock is None:
                        self._connect()
                    self._sock.sendall(data)
                    return True
                except Exception as e:
                    logger.debug(f"IPC 发送失败,重连: {e}")
                    try:
                        if self._sock:
                            self._sock.close()
                    except Exception:
                        pass
                    self._sock = None
            return False

    def send_partial(self, text: str) -> bool:
        """推送中间结果(预编辑区显示)."""
        return self._send({"type": "partial", "text": text})

    def send_final(self, text: str, ack_timeout: float = 2.0) -> bool:
        """推送最终结果并等待插件确认(commit 已执行)."""
        with self._lock:
            if not self._send({"type": "final", "text": text}):
                return False
            if not self._sock:
                return False
            try:
                self._sock.settimeout(ack_timeout)
                buf = b""
                while ack_timeout > 0:
                    chunk = self._sock.recv(512)
                    if not chunk:
                        break
                    buf += chunk
                    if b'"ack"' in buf or b"ack" in buf:
                        return True
            except Exception as e:
                logger.debug(f"等待 ack 失败: {e}")
            finally:
                try:
                    self._sock.settimeout(None)
                except Exception:
                    pass
            return False

