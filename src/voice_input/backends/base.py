"""ASR 后端抽象:定义 daemon 所需的流式会话接口."""

from abc import ABC, abstractmethod
from typing import Callable


class StreamingSession(ABC):
    """一次流式识别会话。与 XunfeiStreamer 的既有行为鸭子类型兼容。"""

    @abstractmethod
    def prepare_session(self) -> None: ...

    @abstractmethod
    def start(self) -> bool: ...

    @abstractmethod
    def send_audio(self, pcm_bytes: bytes) -> None: ...

    @abstractmethod
    def stop(
        self, close_connection: bool = True, final_result_timeout: float = 3.0
    ) -> str: ...

    @abstractmethod
    def cleanup(self) -> None: ...


class ASRBackend(ABC):
    """后端工厂:根据配置创建具体的流式会话。"""

    name: str = "abstract"

    @abstractmethod
    def create_streamer(
        self, config, on_result: Callable[[str, bool], None]
    ) -> StreamingSession: ...


def get_streamer(config, on_result: Callable[[str, bool], None]):
    """按配置实例化后端并创建流式会话(V2 扩展点)。"""
    backend_name = config.backend
    if backend_name == "xunfei":
        from voice_input.backends.xunfei_backend import XunfeiBackend

        return XunfeiBackend().create_streamer(config, on_result)
    if backend_name == "funasr":
        raise NotImplementedError("funasr 本地后端计划于 V2.2 提供")
    raise ValueError(f"未支持的 ASR 后端: {backend_name!r}(可用: xunfei)")

