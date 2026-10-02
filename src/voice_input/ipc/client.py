"""向 fcitx5 voiceim 插件推送流式识别结果的 Unix socket 客户端."""

import json
import logging
import os
import socket
import threading
import time

logger = logging.getLogger(__name__)


def _socket_path() -> str:
    runtime = os.environ.get("XDG_RUNTIME_DIR", "/run/user/1000")
    return os.path.join(runtime, "voice-input", "im.sock")


class VoiceIMClient:
    """与 fcitx5 插件保持长连接,断线自动重连."""

    def __init__(self):
        self._sock: socket.socket | None = None
        # RLock: send_final 内部会嵌套调用 _send,必须可重入
        self._lock = threading.RLock()

    def _connect(self) -> None:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(1.0)  # 连接最多等 1 秒,绝不卡死主线程
        s.connect(_socket_path())
        self._sock = s

    def _wait_ready(self) -> None:
        """等待插件 ready 握手(边缘触发事件循环必须先 arm watcher 再收数据)."""
        self._sock.settimeout(2.0)
        buf = b""
        deadline = time.time() + 2.0
        while time.time() < deadline:
            try:
                chunk = self._sock.recv(256)
            except socket.timeout:
                continue
            if not chunk:
                raise ConnectionError("插件连接已关闭")
            buf += chunk
            if b'"ready"' in buf:
                self._sock.settimeout(None)
                return
        raise TimeoutError("等待 ready 握手超时")

    def _send(self, payload: dict) -> bool:
        # 与 C++ 插件的解析约定严格一致:紧凑分隔符 + 非 ASCII 原样输出
        data = (
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        with self._lock:
            for _ in range(2):  # 一次失败重连重试
                try:
                    if self._sock is None:
                        self._connect()
                        self._wait_ready()
                    self._sock.settimeout(None)
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
                    # 插件明确告知 commit 是否执行:失败则交由回退逻辑
                    from voice_input.timeline import timeline

                    if b'"committed":true' in buf:
                        timeline.mark("IPC ack: committed=true")
                        return True
                    if b'"committed":false' in buf:
                        timeline.mark("IPC ack: committed=false")
                        return False
                        logger.warning("插件 commit 未执行(无焦点输入框),回退粘贴")
                        return False
            except Exception as e:
                logger.debug(f"等待 ack 失败: {e}")
            finally:
                try:
                    self._sock.settimeout(None)
                except Exception:
                    pass
            return False
