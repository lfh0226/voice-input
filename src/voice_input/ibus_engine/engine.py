"""Voice Input IBus engine - 按住 Alt_R 说话，流式预编辑，松开上屏."""

import logging
import os
import select
import threading

import gi

gi.require_version("IBus", "1.0")

from gi.repository import GLib, IBus  # noqa: E402

from voice_input.config import Config  # noqa: E402
from voice_input.recognizer.xunfei import XunfeiStreamer  # noqa: E402
from voice_input.recorder import StreamingRecorder  # noqa: E402

logger = logging.getLogger(__name__)

# evdev/X11 硬件键码：KEY_RIGHTALT
ALT_R_KEYCODE = 100
EVDEV_POLL_TIMEOUT = 0.1

try:
    import evdev

    EVDEV_AVAILABLE = True
except ImportError:
    EVDEV_AVAILABLE = False


class VoiceEngine(IBus.Engine):
    """IBus 引擎：激活后按住 Alt_R 说话，中间结果进预编辑，松开后 commit 上屏."""

    def __init__(self):
        super().__init__()
        self._config = Config()

        self._recorder = StreamingRecorder(
            sample_rate=self._config.recording.get("sample_rate", 16000),
            channels=self._config.recording.get("channels", 1),
            chunk_ms=self._config.recording.get("chunk_ms", 160),
            on_chunk=self._on_audio_chunk,
        )
        self._streamer: XunfeiStreamer | None = None
        self._current_text = ""
        self._recording = False
        self._stopping = False
        self._stop_requested = False
        self._worker: threading.Thread | None = None
        self._evdev_thread: threading.Thread | None = None
        self._evdev_running = False
        self._evdev_devices = []

        log_dir = os.environ.get(
            "XDG_STATE_HOME", os.path.expanduser("~/.local/state")
        )
        log_file = os.path.join(log_dir, "voice-input", "ibus-engine.log")
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[logging.FileHandler(log_file), logging.StreamHandler()],
        )
        logger.info("VoiceEngine 初始化完成")

    # ------------------------------------------------------------------
    # IBus 入口
    # ------------------------------------------------------------------
    def do_process_key_event(self, keyval, keycode, state):
        """拦截 Alt_R：按住开始录音，松开结束并上屏."""
        if keycode != ALT_R_KEYCODE:
            return False

        is_release = bool(state & IBus.ModifierType.RELEASE_MASK)
        logger.debug("Alt_R key event: release=%s", is_release)

        if is_release:
            self._request_stop()
        else:
            self._request_start()
        return True

    def do_enable(self):
        logger.info("voice 输入法引擎已启用（按住 Alt_R 说话，松开上屏）")
        self._start_evdev_listener()

    def do_focus_in(self):
        logger.info("焦点进入（commit/preedit 将作用于当前输入框）")

    def do_focus_out(self):
        logger.info("焦点离开")

    def do_disable(self):
        logger.info("voice 输入法引擎已停用")
        self._stop_evdev_listener()
        if self._recording:
            self._request_stop()

    # ------------------------------------------------------------------
    # evdev 热键监听（GNOME Wayland 下修饰键不会转发给 IM，只能直读 /dev/input）
    # ------------------------------------------------------------------
    def _start_evdev_listener(self):
        if not EVDEV_AVAILABLE or self._evdev_running:
            return
        self._evdev_running = True
        self._evdev_thread = threading.Thread(target=self._evdev_run, daemon=True)
        self._evdev_thread.start()

    def _stop_evdev_listener(self):
        self._evdev_running = False
        for dev in self._evdev_devices:
            try:
                dev.close()
            except Exception:
                pass
        self._evdev_devices = []
        self._evdev_thread = None

    def _evdev_run(self):
        try:
            paths = evdev.list_devices()
            for path in paths:
                try:
                    dev = evdev.InputDevice(path)
                    caps = dev.capabilities()
                    if evdev.ecodes.EV_KEY in caps and (
                        evdev.ecodes.KEY_LEFTALT in caps[evdev.ecodes.EV_KEY]
                        or evdev.ecodes.KEY_RIGHTALT in caps[evdev.ecodes.EV_KEY]
                    ):
                        self._evdev_devices.append(dev)
                except Exception:
                    continue

            if not self._evdev_devices:
                logger.warning("evdev 监听:未找到键盘设备")
                self._evdev_running = False
                return

            logger.info("evdev 监听 %d 个键盘设备", len(self._evdev_devices))
            while self._evdev_running:
                try:
                    readable, _, _ = select.select(self._evdev_devices, [], [], EVDEV_POLL_TIMEOUT)
                except (OSError, ValueError):
                    break
                for dev in readable:
                    try:
                        for event in dev.read():
                            if not self._evdev_running:
                                break
                            if event.type != evdev.ecodes.EV_KEY:
                                continue
                            if event.code == evdev.ecodes.KEY_RIGHTALT:
                                if event.value == 1:
                                    logger.info("evdev: Alt_R 按下")
                                    self._request_start()
                                elif event.value == 0:
                                    logger.info("evdev: Alt_R 松开")
                                    self._request_stop()
                    except Exception:
                        continue
        except Exception:
            logger.exception("evdev 监听线程异常")

    # ------------------------------------------------------------------
    # 录音会话（后台线程，避免阻塞 IBus 主循环）
    # ------------------------------------------------------------------
    def _request_start(self):
        if self._recording or self._stopping:
            return
        self._recording = True
        self._worker = threading.Thread(target=self._session_worker, daemon=True)
        self._worker.start()

    def _request_stop(self):
        # 通过置位标志让会话线程进入收尾阶段
        self._stop_requested = True

    def _session_worker(self):
        """一次完整的录音会话：按住期间推流，收到停止标志后收尾."""
        self._stop_requested = False
        self._current_text = ""
        logger.info("开始录音会话")

        streamer = XunfeiStreamer(
            app_id=self._config.xunfei.get("app_id", ""),
            api_key=self._config.xunfei.get("api_key", ""),
            api_secret=self._config.xunfei.get("api_secret", ""),
            language=self._config.xunfei.get("language", "zh_cn"),
            accent=self._config.xunfei.get("accent", "mandarin"),
            on_result=self._on_result,
            vad_eos=self._config.xunfei.get("vad_eos", 5000),
            max_audio_queue_size=self._config.xunfei.get("max_audio_queue_size", 400),
            batch_chunks=self._config.xunfei.get("batch_chunks", 2),
        )
        self._streamer = streamer

        try:
            streamer.prepare_session()
            if not self._recorder.start():
                logger.error("启动录音失败")
                self._finish(stopped=False)
                return
            if not streamer.start():
                logger.error("启动识别器失败")
                self._recorder.stop()
                self._finish(stopped=False)
                return

            # 等待 Alt_R 松开
            while not self._stop_requested:
                GLib.usleep(50_000)  # 50ms 轮询，阻塞的是工作线程而非主循环
        finally:
            self._finish(stopped=True, streamer=streamer)

    def _finish(self, stopped: bool, streamer: XunfeiStreamer | None = None):
        """收尾：停录音、等最终结果、commit 上屏（后台线程内执行）."""
        self._recording = False
        self._stopping = True
        try:
            self._recorder.stop()
            if stopped and streamer:
                final_text = streamer.stop(close_connection=True, final_result_timeout=3.0)
                text = final_text or self._current_text
                logger.info("识别完成：%d 个字符", len(text))
                if text:
                    GLib.idle_add(self._commit_and_clear, text)
                else:
                    logger.warning("未识别到文字")
                    GLib.idle_add(self._clear_preedit)
            else:
                if streamer:
                    streamer.stop(close_connection=True, final_result_timeout=0.5)
                GLib.idle_add(self._clear_preedit)
        except Exception:
            logger.exception("收尾阶段异常")
            GLib.idle_add(self._clear_preedit)
        finally:
            self._streamer = None
            self._stopping = False

    # ------------------------------------------------------------------
    # 回调（各自工作线程 → GLib 主循环）
    # ------------------------------------------------------------------
    def _on_audio_chunk(self, pcm_bytes: bytes):
        if self._streamer and self._recording:
            self._streamer.send_audio(pcm_bytes)

    def _on_result(self, text: str, is_final: bool):
        self._current_text = text
        GLib.idle_add(self._update_preedit, text)

    # ------------------------------------------------------------------
    # UI（GLib 主循环内执行）
    # ------------------------------------------------------------------
    def _update_preedit(self, text: str):
        if not text:
            return False
            # 流式中间结果 → 预编辑区（灰字，可退格修改）
        ibus_text = IBus.Text.new_from_string(text)
        self.update_preedit_text(ibus_text, len(text), True)
        return False

    def _commit_and_clear(self, text: str):
        self.commit_text(IBus.Text.new_from_string(text))
        self._clear_preedit()
        return False

    def _clear_preedit(self):
        self.update_preedit_text(IBus.Text.new_from_string(""), 0, False)
        return False
