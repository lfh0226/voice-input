"""可插拔 ASR 后端层:更换识别服务只需实现 StreamingSession 接口."""

from voice_input.backends.base import get_streamer

__all__ = ["get_streamer"]
