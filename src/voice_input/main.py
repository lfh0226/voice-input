#!/usr/bin/env python3
"""Voice Input - 流式语音输入工具"""

import argparse
import shutil
import logging
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

from voice_input.config import Config, get_config
from voice_input.hotkey import HotkeyListener
from voice_input.ipc.client import VoiceIMClient
from voice_input.resident import ASRSessionRelay
from voice_input.recorder import StreamingRecorder
from voice_input.vad import EnergyVAD, VADConfig
from voice_input.backends import get_streamer
from voice_input.timeline import timeline
from voice_input.backends.base import StreamingSession
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
        self.im_client = VoiceIMClient()
        self._committed_len = 0   # 本次会话已通过插件上屏的字符数
        self._last_commit_ts = 0.0
        self._fcitx5_remote = shutil.which("fcitx5-remote")

        # 流式录音器
        self.recorder = StreamingRecorder(
            sample_rate=config.recording.get("sample_rate", 16000),
            channels=config.recording.get("channels", 1),
            chunk_ms=config.recording.get("chunk_ms", 40),
            on_chunk=self._on_audio_chunk,
        )

        # 流式识别器
        self.streamer: Optional[StreamingSession] = None
        self.current_text = ""
        self._is_recording = False
        self._focus_window = None  # 记住焦点窗口用于输入
        self._reuse_connection = config.xunfei.get("reuse_connection", False)
        self._final_result_timeout = config.xunfei.get("final_result_timeout", 3.0)

        # 快捷键监听器
        self.hotkey_listener: Optional[HotkeyListener] = None

        # V2.1: relay 提供预热会话池(WS 常驻保温,零数据流出)。
        # 热键按下 = 门控打开,音频才写入会话;空闲期仅保持连接,合规零采集。
        self._resident_enabled = bool(config.resident.get("enabled", False))
        self.resident_vad: EnergyVAD | None = None
        self.resident_relay: ASRSessionRelay | None = None
        self._resident_committed_len = 0
        # 热键门控状态
        self._relay_gate = False
        self._gate_prebuffer: list[bytes] = []
        self._relay_warmed_at = 0.0
        if True:
            resident_config = config.resident
            vad_config = VADConfig(
                sample_rate=config.recording.get("sample_rate", 16000),
                frame_ms=config.recording.get("chunk_ms", 80),
                speech_rms_threshold=resident_config.get(
                    "speech_rms_threshold", 500.0
                ),
                start_frames=resident_config.get("start_frames", 2),
                end_silence_ms=resident_config.get("end_silence_ms", 700),
                min_speech_ms=resident_config.get("min_speech_ms", 240),
                prebuffer_ms=resident_config.get("prebuffer_ms", 240),
                max_segment_ms=resident_config.get("max_segment_ms", 60_000),
            )
            if self._resident_enabled:
                self.resident_vad = EnergyVAD(
                    vad_config,
                    on_segment_start=self._on_resident_segment_start,
                    on_speech=self._on_resident_speech,
                    on_segment_end=self._on_resident_segment_end,
                )
            self.resident_relay = ASRSessionRelay(
                create_session=lambda: self._create_streamer(
                    self._on_relay_result
                ),
                on_result=lambda text, final: None,
                on_final=self._on_relay_final,
                final_result_timeout=config.xunfei.get(
                    "final_result_timeout", 3.0
                ),
                reuse_connection=True,
            )
            self.resident_relay.warm()
            self._relay_warmed_at = time.time()

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

        # 毫秒级时间线(可用 logging.timeline: false 关闭)
        timeline.set_enabled(bool(log_config.get("timeline", True)))
        from voice_input.logger_config import get_log_file

        timeline.use_file(str(get_log_file()).replace("voice-input.log", "timeline.log"))

        if level == logging.DEBUG:
            logger.debug("调试模式已启用")
            logger.debug(f"日志配置: {log_config}")

    def _on_audio_chunk(self, pcm_bytes: bytes):
        """音频块回调 - 热键门控:仅按住 Alt_R 期间音频才离开设备"""
        if self._relay_gate:
            if self.resident_relay and self.resident_relay.is_ready:
                # 连接就绪:先冲刷门控期间积压的音频,再送当前块
                while self._gate_prebuffer:
                    self.resident_relay.send_audio(self._gate_prebuffer.pop(0))
                self.resident_relay.send_audio(pcm_bytes)
            else:
                # 预热会话尚未就绪(罕见):本地暂存,就绪后补发
                self._gate_prebuffer.append(pcm_bytes)
            return
        if self.resident_vad:
            self.resident_vad.feed(pcm_bytes)
            return

        if self.streamer and self._is_recording:
            # debug模式下打印音频块信息
            if self.config.logging_config.get("show_audio_chunks"):
                logger.debug(f"音频块: {len(pcm_bytes)} bytes")
            self.streamer.send_audio(pcm_bytes)

    def _create_streamer(self, on_result=None):
        """通过后端抽象层创建流式会话(V2:可插拔 ASR 后端)。"""
        return get_streamer(self.config, on_result or self._on_result)

    def _get_streamer(self):
        """Return the active streamer, creating one when needed."""
        if self.streamer is None:
            self.streamer = self._create_streamer()
        return self.streamer

    def _on_result(self, text: str, is_final: bool):
        """识别结果回调 - 边说边显示"""
        self.current_text = text

        # 流式中间结果 → fcitx5 预编辑区(只发未上屏的增量部分)
        if self._is_recording and not is_final and text:
            elapsed = time.time() - self._session_t0
            logger.info("T+%.2fs 中间结果 len=%d", elapsed, len(text))
            remainder = text[self._committed_len :]
            if remainder:
                self.im_client.send_partial(remainder)
            # 长语音分段自动上屏:每累计 ≥10 个新字且距上次提交 ≥2 秒
            if (
                len(text) - self._committed_len >= 10
                and time.time() - self._last_commit_ts >= 2.0
            ):
                segment = text[self._committed_len :]
                if self.im_client.send_final(segment):
                    timeline.mark(f"分段上屏 {len(segment)} 字")
                    logger.info("分段上屏 %d 字(累计 %d)", len(segment), self._committed_len + len(segment))
                    self._committed_len = len(text)
                    self._last_commit_ts = time.time()

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
        timeline.reset("热键按下")

        # 预热会话接力:回收过期空闲会话,保证 Alt 按下即有热连接
        if self.resident_relay:
            self.resident_relay.recycle_if_stale(max_age_s=12.0)
            self._relay_gate = True
            self._resident_committed_len = 0
            self._last_commit_ts = time.time()

        # 切换到 voice 输入法(为 commit 做准备),记住原 IM 以便恢复
        if self._fcitx5_remote:
            try:
                subprocess.run(
                    [self._fcitx5_remote, "-s", "voice"], capture_output=True, timeout=1
                )
                logger.debug("切换到 voice IM")
                timeline.mark("IM 已切到 voice + Shift 敲击注入")                # 切 IM 会让应用侧输入上下文 focusOut;注入一次无害的 Shift
                # 敲击强制输入上下文重新挂到 voice 引擎上,否则 final 时
                # focusedIC 为 null,commit 会静默丢失
                if shutil.which("ydotool"):
                    subprocess.run(
                        ["ydotool", "key", "42:1", "42:0"],
                        capture_output=True,
                        timeout=1,
                    )
            except Exception as e:
                logger.debug(f"切换 IM 失败: {e}")

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
        self._session_t0 = time.time()
        self._committed_len = 0
        self._last_commit_ts = 0.0

        # 播放开始提示音
        self.sound.play_start()

        # 创建流式识别器
        backend = self.config.backend
        if backend != "xunfei":
            logger.error(f"不支持的后端: {backend}")
            return

        # 先开始录音，再连接 WebSocket。连接期间的音频会进入 streamer 队列，避免漏掉开头。
        # 连接失败(网络抖动)自动重试一次
        started = False
        for attempt in range(2):
            streamer = self._get_streamer()
            streamer.prepare_session()
            self._is_recording = True
            if not self.recorder.start():
                logger.error("启动录音失败")
                self._is_recording = False
                self.sound.play_error()
                return
            if streamer.start():
                started = True
                break
            logger.warning(f"启动识别器失败(第 {attempt + 1} 次)")
            self._is_recording = False
            self.recorder.stop()
            if not self._reuse_connection:
                self.streamer = None
            if attempt == 0:
                time.sleep(0.5)
        if not started:
            logger.error("启动识别器失败(已重试)")
            self.sound.play_error()

    def _on_relay_result(self, text: str, is_final: bool) -> None:
        """relay 会话的流式结果回调(热键门控模式)."""
        self._on_resident_result(text, is_final)

    def _on_relay_final(self, text: str) -> None:
        """relay 会话最终结果:插件上屏,失败回退剪贴板(热键门控有焦点窗口)."""
        remainder = text[self._resident_committed_len :]
        self._resident_committed_len = max(0, len(text))
        if not remainder:
            return
        delivered = self.im_client.send_final(remainder)
        timeline.mark(f"插件 commit delivered={delivered} len={len(remainder)}")
        if delivered:
            logger.info("会话已通过插件上屏 %d 个字符", len(remainder))
            return
        if self._focus_window:
            logger.warning("插件上屏失败,回退剪贴板粘贴 %d 个字符", len(remainder))
            self.text_input.input_text(remainder, self._focus_window)
        else:
            logger.error("会话上屏失败,已丢弃 %d 个字符", len(remainder))

    def _on_resident_segment_start(self, pcm_bytes: bytes) -> None:
        """Feed speech prebuffer into the already-warm ASR session."""
        self._resident_committed_len = 0
        if self.resident_relay and pcm_bytes:
            self.resident_relay.send_audio(pcm_bytes)

    def _on_resident_speech(self, pcm_bytes: bytes) -> None:
        """Stream one voiced VAD frame to the active ASR session."""
        if self.resident_relay:
            self.resident_relay.send_audio(pcm_bytes)

    def _on_resident_segment_end(self) -> None:
        """Finalize the current segment while warming the next session."""
        if self.resident_relay:
            self.resident_relay.finish_segment()

    def _on_resident_result(self, text: str, is_final: bool) -> None:
        """Render resident ASR partials and retain incremental commit state."""
        self.current_text = text
        if is_final or not text:
            return

        remainder = text[self._resident_committed_len :]
        if remainder:
            self.im_client.send_partial(remainder)

        # Reuse the long-speech policy from hotkey mode: commit a stable
        # prefix so a very long utterance is not held in preedit forever.
        if (
            len(text) - self._resident_committed_len >= 10
            and time.time() - self._last_commit_ts >= 2.0
        ):
            segment = text[self._resident_committed_len :]
            if self.im_client.send_final(segment):
                self._resident_committed_len = len(text)
                self._last_commit_ts = time.time()

    def _on_resident_final(self, text: str) -> None:
        """Commit the final remainder produced by a relayed session."""
        remainder = text[self._resident_committed_len :]
        self._resident_committed_len = max(0, len(text))
        if not remainder:
            return

        delivered = self.im_client.send_final(remainder)
        if delivered:
            logger.info("常驻会话已上屏 %d 个字符", len(remainder))
            return

        # Resident mode intentionally has no remembered focus window from a
        # hotkey press. Clipboard fallback would be unsafe outside an explicit
        # user gesture, so surface the failure instead of typing blindly.
        logger.error("常驻会话插件上屏失败,已丢弃 %d 个字符", len(remainder))

    def _on_hotkey_release(self):
        """快捷键释放 - 停止录音并输入文字"""
        if not self._is_recording:
            return

        self._is_recording = False
        timeline.mark("热键松开,停止本地采集")

        # 停止本地采集(合规:按键松开即停止采集),会话在后台完成 final
        self.recorder.stop()

        if self._relay_gate:
            self._relay_gate = False
            if self.resident_relay:
                self.resident_relay.finish_segment()
            return

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

            text_to_input = (final_text or self.current_text)[self._committed_len :]
            if text_to_input:
                # 优先走 fcitx5 插件直接 commit(零粘贴);失败回退剪贴板粘贴
                delivered = self.im_client.send_final(text_to_input)
                if delivered:
                    logger.info("已通过 fcitx5 插件直接上屏 %d 个字符", len(text_to_input))
                    success = True
                else:
                    logger.info("插件不可用,回退剪贴板粘贴 %d 个字符", len(text_to_input))
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

        if self._resident_enabled:
            logger.warning(
                "常驻监听已启用:麦克风将持续采集音频。识别文本仅发送到配置的 ASR 后端; "
                "如需停止,请禁用 resident.enabled 并重启服务。"
            )
        logger.info("启动流式语音输入...")

        # 创建 fcitx5 插件套接字目录
        try:
            import os as _os

            _runtime = _os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{_os.getuid()}")
            _os.makedirs(_os.path.join(_runtime, "voice-input"), exist_ok=True)
        except Exception as e:
            logger.warning(f"创建 IPC 目录失败: {e}")

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

        # 音频链路自检：提前暴露设备/环境问题（否则要等到第一次按键才报错）
        audio_ok, audio_message = StreamingRecorder.probe()
        if audio_ok:
            logger.info(f"音频输入就绪: {audio_message}")
        else:
            logger.error(f"音频输入不可用: {audio_message}")
            print(
                "\n\033[31m❌ 音频输入不可用\033[0m\n"
                f"   {audio_message}\n"
                "   提示：请在桌面会话（终端或登录自启动）中运行，"
                "确保 XDG_RUNTIME_DIR / WAYLAND_DISPLAY 等会话变量存在。\n",
                flush=True,
            )

        if self._resident_enabled:
            # Resident mode owns the microphone continuously. Keeping the
            # hotkey listener active would race on recorder.start/stop.
            if not self.recorder.start():
                logger.error("常驻监听启动录音失败")
                self.resident_relay.stop()
                return False
            self.resident_relay.warm()
            self._running = True
            logger.info("常驻监听已就绪,等待本地 VAD 触发识别")
            return True

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

        if self.resident_vad:
            self.resident_vad.flush()
            self.resident_vad = None
        if self.resident_relay:
            self.resident_relay.stop()
            self.resident_relay = None
        if self._resident_enabled:
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
