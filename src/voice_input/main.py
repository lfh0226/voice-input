#!/usr/bin/env python3
"""Voice Input - 流式语音输入工具"""

import argparse
import logging
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

from voice_input.config import Config, get_config
from voice_input.hotkey import HotkeyListener
from voice_input.recorder import StreamingRecorder
from voice_input.recognizer.xunfei import XunfeiStreamer
from voice_input.sound import SoundFeedback
from voice_input.typer import TextInput

# 日志级别映射
LOG_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}

LOW_LATENCY_FINAL_TIMEOUT = 0.2

# 默认日志配置（将在应用启动时根据配置更新）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


class StreamingVoiceInput:
    """流式语音输入应用"""

    def __init__(self, config: Config):
        """初始化流式语音输入

        Args:
            config: 配置实例
        """
        self.config = config

        # 根据配置设置日志级别
        self._setup_logging()

        # 初始化组件
        self.sound = SoundFeedback(enabled=config.sound.get("enabled", True))
        self.text_input = TextInput(
            method=config.input_config.get("method", "type"),
            type_delay=config.input_config.get("type_delay", 0.005),
        )

        # 流式录音器
        self.recorder = StreamingRecorder(
            sample_rate=config.recording.get("sample_rate", 16000),
            channels=config.recording.get("channels", 1),
            chunk_ms=config.recording.get("chunk_ms", 40),
            on_chunk=self._on_audio_chunk,
        )

        # 流式识别器
        self.streamer: Optional[XunfeiStreamer] = None
        self.current_text = ""
        self._is_recording = False
        self._focus_window = None  # 记住焦点窗口用于输入
        self._reuse_connection = config.xunfei.get("reuse_connection", False)
        self._final_result_timeout = config.xunfei.get("final_result_timeout", 3.0)

        # 快捷键监听器
        self.hotkey_listener: Optional[HotkeyListener] = None

        # 运行状态
        self._running = False

    def _setup_logging(self):
        """根据配置设置日志级别"""
        log_config = self.config.logging_config
        level_name = log_config.get("level", "info").lower()
        level = LOG_LEVELS.get(level_name, logging.INFO)

        # 更新根日志级别
        logging.getLogger().setLevel(level)
        logger.setLevel(level)

        if level == logging.DEBUG:
            logger.debug("调试模式已启用")
            logger.debug(f"日志配置: {log_config}")

    def _on_audio_chunk(self, pcm_bytes: bytes):
        """音频块回调 - 发送到流式识别器"""
        if self.streamer and self._is_recording:
            # debug模式下打印音频块信息
            if self.config.logging_config.get("show_audio_chunks"):
                logger.debug(f"音频块: {len(pcm_bytes)} bytes")
            self.streamer.send_audio(pcm_bytes)

    def _create_streamer(self) -> XunfeiStreamer:
        """Create a Xunfei streamer from the current configuration."""
        return XunfeiStreamer(
            app_id=self.config.xunfei.get("app_id", ""),
            api_key=self.config.xunfei.get("api_key", ""),
            api_secret=self.config.xunfei.get("api_secret", ""),
            language=self.config.xunfei.get("language", "zh_cn"),
            accent=self.config.xunfei.get("accent", "mandarin"),
            on_result=self._on_result,
            vad_eos=self.config.xunfei.get("vad_eos", 5000),
            max_audio_queue_size=self.config.xunfei.get("max_audio_queue_size", 400),
            batch_chunks=self.config.xunfei.get("batch_chunks", 2),
        )

    def _get_streamer(self) -> XunfeiStreamer:
        """Return the active streamer, creating one when needed."""
        if self.streamer is None:
            self.streamer = self._create_streamer()
        return self.streamer

    def _on_result(self, text: str, is_final: bool):
        """识别结果回调 - 边说边显示"""
        self.current_text = text

        # 识别内容可能包含隐私，默认只显示状态和长度
        if self.config.logging_config.get("show_recognized_text"):
            status = "最终结果" if is_final else "中间结果"
            logger.debug("[%s] 识别文本长度: %s", status, len(text))

        if text:
            print(f"\r\033[K\033[32m🎤 已识别 {len(text)} 个字符\033[0m", end="", flush=True)
        if is_final:
            print()  # 换行
            print(f"\033[33m✅ 已完成识别，共 {len(text)} 个字符\033[0m", flush=True)

    def _on_hotkey_press(self):
        """快捷键按下 - 开始录音"""
        if self._is_recording:
            return

        # 记住当前焦点窗口（用于后续输入）
        try:
            result = subprocess.run(
                ["xdotool", "getwindowfocus"], capture_output=True, text=True, timeout=0.5
            )
            if result.returncode == 0:
                self._focus_window = result.stdout.strip()
                logger.debug(f"记住焦点窗口: {self._focus_window}")
        except Exception as e:
            logger.debug(f"无法获取焦点窗口: {e}")
            self._focus_window = None

        print("\n🔴 开始录音，请说话...", flush=True)
        self.current_text = ""

        # 播放开始提示音
        self.sound.play_start()

        # 创建流式识别器
        backend = self.config.backend
        if backend != "xunfei":
            logger.error(f"不支持的后端: {backend}")
            return

        streamer = self._get_streamer()
        streamer.prepare_session()

        # 先开始录音，再连接 WebSocket。连接期间的音频会进入 streamer 队列，避免漏掉开头。
        self._is_recording = True
        if not self.recorder.start():
            logger.error("启动录音失败")
            self._is_recording = False
            self.sound.play_error()
            return

        if not streamer.start():
            logger.error("启动识别器失败")
            self._is_recording = False
            self.recorder.stop()
            self.sound.play_error()
            if not self._reuse_connection:
                self.streamer = None

    def _on_hotkey_release(self):
        """快捷键释放 - 停止录音并输入文字"""
        if not self._is_recording:
            return

        self._is_recording = False

        # 停止录音
        self.recorder.stop()

        # 播放结束提示音
        self.sound.play_end()

        # 获取最终结果
        if self.streamer:
            final_result_timeout = (
                LOW_LATENCY_FINAL_TIMEOUT if self.current_text else self._final_result_timeout
            )
            final_text = self.streamer.stop(
                close_connection=not self._reuse_connection,
                final_result_timeout=final_result_timeout,
            )
            if not self._reuse_connection:
                self.streamer = None

            text_to_input = final_text or self.current_text
            if text_to_input:
                logger.info("识别完成，准备输入 %s 个字符", len(text_to_input))
                success = self.text_input.input_text(text_to_input, self._focus_window)
                if not success:
                    logger.error("文字输入失败")
                    print(f"\033[31m❌ 输入失败，已识别 {len(text_to_input)} 个字符\033[0m")
            else:
                logger.warning("未识别到文字")

    def start(self) -> bool:
        """启动语音输入

        Returns:
            是否成功启动
        """
        if self._running:
            return True

        logger.info("启动流式语音输入...")

        # 检查配置
        backend = self.config.backend
        if backend == "xunfei":
            if not all(
                [
                    self.config.xunfei.get("app_id"),
                    self.config.xunfei.get("api_key"),
                    self.config.xunfei.get("api_secret"),
                ]
            ):
                logger.error("讯飞API配置不完整，请检查config.yaml")
                return False
        else:
            logger.error(f"不支持的后端: {backend}")
            return False

        # 启动快捷键监听
        self.hotkey_listener = HotkeyListener(
            hotkey=self.config.hotkey.get("trigger", "alt"),
            on_press=self._on_hotkey_press,
            on_release=self._on_hotkey_release,
            mode=self.config.hotkey.get("mode", "hold"),
        )
        self.hotkey_listener.start()

        self._running = True
        logger.info(f"语音输入已就绪，按住 {self.config.hotkey.get('trigger', 'alt')} 开始录音")
        return True

    def stop(self):
        """停止语音输入"""
        if not self._running:
            return

        logger.info("停止语音输入...")

        # 停止录音
        if self._is_recording:
            self._is_recording = False
            self.recorder.stop()

        # 停止识别器
        if self.streamer:
            self.streamer.cleanup()
            self.streamer = None

        # 停止快捷键监听
        if self.hotkey_listener:
            self.hotkey_listener.stop()
            self.hotkey_listener = None

        self._running = False
        logger.info("语音输入已停止")

    def run(self):
        """运行应用（阻塞）"""
        if not self.start():
            sys.exit(1)

        # 设置信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        # 保持运行
        try:
            while self._running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def _signal_handler(self, signum: int, frame: Any):
        """处理终止信号"""
        logger.info(f"收到信号 {signum}")
        self.stop()
        sys.exit(0)


def main():
    """主入口"""
    parser = argparse.ArgumentParser(
        description="Voice Input - 流式语音输入工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  voice-input                    # 使用默认配置启动
  voice-input --config my.yaml   # 使用指定配置文件
  voice-input --list-devices     # 列出音频输入设备
        """,
    )

    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        help="配置文件路径",
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="列出可用的音频输入设备",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="显示详细日志",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="lb-voice 1.0.0",
    )

    args = parser.parse_args()

    # 设置日志级别
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # 列出设备并退出
    if args.list_devices:
        print("可用的音频输入设备:")
        print("-" * 60)
        devices = (
            StreamingRecorder.list_devices() if hasattr(StreamingRecorder, "list_devices") else []
        )
        if not devices:
            # 使用AudioRecorder的静态方法
            from voice_input.recorder import AudioRecorder

            devices = AudioRecorder.list_devices()
        for dev in devices:
            print(f"  [{dev['index']}] {dev['name']}")
            print(f"      声道: {dev['channels']}, 采样率: {dev['sample_rate']}")
        return

    # 加载配置
    config = get_config(args.config)

    # 运行应用
    app = StreamingVoiceInput(config)
    app.run()


if __name__ == "__main__":
    main()
