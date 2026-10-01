"""讯飞语音听写流式识别"""

import base64
import hashlib
import hmac
import json
import logging
import queue
import threading
import time
from typing import Callable, Optional
from urllib.parse import urlencode, urlparse

import websocket

logger = logging.getLogger(__name__)


class XunfeiStreamer:
    """讯飞流式语音识别 - 支持实时边说边出字"""

    WS_URL = "wss://iat-api.xfyun.cn/v2/iat"

    def __init__(
        self,
        app_id: str,
        api_key: str,
        api_secret: str,
        language: str = "zh_cn",
        accent: str = "mandarin",
        on_result: Optional[Callable[[str, bool], None]] = None,
        vad_eos: int = 60000,  # 60 秒，支持长语音  # 语音结束静默时长 (毫秒)，默认 10 秒，防止提前结束
        max_audio_queue_size: int = 400,
        batch_chunks: int = 2,
    ):
        """初始化讯飞流式识别器

        Args:
            app_id: 讯飞应用ID
            api_key: 讯飞API Key
            api_secret: 讯飞API Secret
            language: 语言 (zh_cn, en_us)
            accent: 方言 (mandarin, cantonese)
            on_result: 结果回调 (text, is_final)
            vad_eos: 语音结束静默时长(毫秒), 默认5000
        """
        self.app_id = app_id
        self.api_key = api_key
        self.api_secret = api_secret
        self.language = language
        self.accent = accent
        self.on_result = on_result
        self.vad_eos = vad_eos

        self._ws: Optional[websocket.WebSocketApp] = None
        self._audio_queue: queue.Queue = queue.Queue()
        self._result_text = ""
        self._result_parts: list[str] = []  # 用于动态修正
        self._running = False
        self._user_stopped = True
        self._server_final = False
        self._end_frame_sent = False
        self._stream_t0 = time.time()
        self._connected = False
        self._thread: Optional[threading.Thread] = None
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._state_lock = threading.RLock()
        self._last_activity = time.time()
        self._max_audio_queue_size = max_audio_queue_size
        self._audio_frames_sent = 0
        self._audio_bytes_sent = 0
        self._messages_received = 0
        self.batch_chunks = max(1, batch_chunks)

    def _create_url(self) -> str:
        """生成鉴权URL"""
        # RFC1123格式时间戳
        date = time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime())
        parsed = urlparse(self.WS_URL)

        # 签名字符串
        sig_origin = f"host: {parsed.netloc}\ndate: {date}\nGET {parsed.path} HTTP/1.1"
        sig_sha = hmac.new(
            self.api_secret.encode("utf-8"),
            sig_origin.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        signature = base64.b64encode(sig_sha).decode()

        # authorization
        auth_origin = (
            f'api_key="{self.api_key}", algorithm="hmac-sha256", '
            f'headers="host date request-line", signature="{signature}"'
        )
        authorization = base64.b64encode(auth_origin.encode("utf-8")).decode()

        params = {"authorization": authorization, "date": date, "host": parsed.netloc}
        return self.WS_URL + "?" + urlencode(params)

    def _on_message(self, ws, message):
        """处理识别结果"""
        try:
            self._messages_received += 1
            data = json.loads(message)
            code = data.get("code")

            if code != 0:
                logger.error(f"讯飞识别错误: {data}")
                return

            result_data = data.get("data", {})
            status = result_data.get("status", 0)
            result = result_data.get("result", {})

            # 解析识别文字
            ws_list = result.get("ws", [])
            text_parts = []
            for ws_item in ws_list:
                for cw in ws_item.get("cw", []):
                    text_parts.append(cw.get("w", ""))
            text = "".join(text_parts)

            # 动态修正处理 (dwa=wpgs)
            pgs = result.get("pgs")
            sn = result.get("sn", 0)

            if pgs == "rpl":
                # 替换模式: 替换指定范围的结果
                rg = result.get("rg", [0, 0])
                if len(self._result_parts) > rg[0]:
                    # 替换rg范围内的内容
                    self._result_parts = self._result_parts[: rg[0]] + [text]
            elif pgs == "apd" or not pgs:
                # 追加模式
                if sn >= len(self._result_parts):
                    self._result_parts.append(text)
                else:
                    self._result_parts[sn] = text

            # 合并所有部分
            self._result_text = "".join(self._result_parts)

            # 回调
            is_final = status == 2
            if self.on_result and self._result_text:
                self.on_result(self._result_text, is_final)

            if is_final:
                logger.info("识别完成（服务端VAD），结果长度: %s", len(self._result_text))
                self._server_final = True
                # 不设置 _running=False，让用户控制录音结束

        except Exception as e:
            logger.error(f"解析识别结果失败: {e}")

    def _on_error(self, ws, error):
        logger.error(f"WebSocket错误: {error}")
        self._running = False
        self._user_stopped = True

    def _on_close(self, ws, close_status_code, close_msg):
        logger.debug(f"WebSocket关闭: {close_status_code} {close_msg}")
        self._connected = False
        self._running = False
        self._user_stopped = True

    def _send_first_frame(self) -> None:
        """Send the first frame for a recognition session."""
        if not self._ws or not self._connected:
            return

        frame = {
            "common": {"app_id": self.app_id},
            "business": {
                "language": self.language,
                "domain": "iat",
                "accent": self.accent,
                "dwa": "wpgs",  # 开启动态修正
                "vad_eos": self.vad_eos,  # 语音结束静默时长(毫秒)
                "pd": "result",  # 不启用服务端 VAD，由用户控制结束
            },
            "data": {
                "status": 0,  # 首帧
                "format": "audio/L16;rate=16000",
                "encoding": "raw",
                "audio": "",
            },
        }
        self._ws.send(json.dumps(frame))
        self._last_activity = time.time()

    def _start_audio_thread(self) -> None:
        """Start the audio sender thread if needed."""
        if not self._thread or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._send_audio_loop, daemon=True)
            self._thread.start()

    def _on_open(self, ws):
        """连接建立，发送首帧"""
        logger.debug("WebSocket连接建立")
        self._connected = True
        self._running = True
        self._send_first_frame()
        self._start_audio_thread()

    def _send_end_frame(self) -> None:
        """Send the end frame for the current recognition session."""
        if self._end_frame_sent:
            return
        if self._ws and self._connected:
            frame = {"data": {"status": 2, "audio": ""}}
            self._ws.send(json.dumps(frame))
            self._end_frame_sent = True
            logger.debug("发送结束帧")
            self._last_activity = time.time()

    def _send_audio_loop(self):
        """音频发送循环 - 批量编码，减少 base64/json 次数"""
        batch_buffer = bytearray()
        chunks_in_batch = 0

        while self._running and not self._user_stopped:
            try:
                audio_chunk = self._audio_queue.get(timeout=0.5)
                if audio_chunk is None:
                    if batch_buffer:
                        self._send_audio_frame(bytes(batch_buffer))
                        batch_buffer.clear()
                        chunks_in_batch = 0
                    self._send_end_frame()
                    break

                batch_buffer.extend(audio_chunk)
                chunks_in_batch += 1

                if chunks_in_batch >= self.batch_chunks:
                    self._send_audio_frame(bytes(batch_buffer))
                    if self._stream_t0:
                        logger.info("T+%.2fs 音频批次 %dms/%d字节",
                                    time.time() - self._stream_t0,
                                    chunks_in_batch * self.chunk_ms,
                                    len(batch_buffer))
                    batch_buffer.clear()
                    chunks_in_batch = 0

            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"发送音频失败: {e}")
                break

        # 如果线程退出但还有残留数据，尝试发送
        if batch_buffer:
            self._send_audio_frame(bytes(batch_buffer))

    def _send_audio_frame(self, audio_bytes: bytes, status: int = 1):
        """统一生成帧并发送，避免重复编码逻辑"""
        if not audio_bytes or not self._ws or not self._connected:
            return

        audio_b64 = base64.b64encode(audio_bytes).decode()
        frame = {
            "data": {
                "status": status,
                "format": "audio/L16;rate=16000",
                "encoding": "raw",
                "audio": audio_b64,
            }
        }
        self._ws.send(json.dumps(frame))
        self._audio_frames_sent += 1
        self._audio_bytes_sent += len(audio_bytes)
        self._last_activity = time.time()

    def _queue_kwargs(self) -> dict:
        """Return queue options for audio buffering."""
        queue_kwargs = {}
        if self._max_audio_queue_size > 0:
            queue_kwargs["maxsize"] = self._max_audio_queue_size
        return queue_kwargs

    def reset(self):
        """重置识别状态，准备新的识别会话（复用连接）"""
        self._result_text = ""
        self._result_parts = []
        self._user_stopped = False
        self._server_final = False
        self._end_frame_sent = False
        self._audio_frames_sent = 0
        self._audio_bytes_sent = 0
        self._messages_received = 0
        self._running = True

        # 清空音频队列
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                break

    def prepare_session(self) -> None:
        """Prepare a recognition session before the WebSocket is connected."""
        with self._state_lock:
            self._audio_queue = queue.Queue(**self._queue_kwargs())
            self.reset()

    def start(self) -> bool:
        """开始识别会话

        Returns:
            是否成功启动
        """
        queue_kwargs = self._queue_kwargs()

        with self._state_lock:
            if self._user_stopped:
                self._audio_queue = queue.Queue(**queue_kwargs)
                self.reset()

            if self._ws and self._connected:
                try:
                    self._send_first_frame()
                    self._start_audio_thread()
                    return True
                except Exception as e:
                    logger.warning(f"复用 WebSocket 连接失败，将重新连接: {e}")
                    self.cleanup()
                    self._audio_queue = queue.Queue(**queue_kwargs)
                    self.reset()

        try:
            url = self._create_url()

            with self._state_lock:
                self._ws = websocket.WebSocketApp(
                    url,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                )

            # 后台运行WebSocket
            ws_thread = threading.Thread(target=self._ws.run_forever, daemon=True)
            ws_thread.start()

            # 等待连接建立
            for _ in range(50):  # 最多等待5秒
                if self._connected:
                    return True
                time.sleep(0.1)

            logger.error("WebSocket连接超时")
            self.cleanup()
            return False

        except Exception as e:
            logger.error(f"启动识别会话失败: {e}")
            self.cleanup()
            return False

    def send_audio(self, audio_data: bytes):
        """发送音频数据

        Args:
            audio_data: PCM音频数据 (16kHz, 16bit, mono)
        """
        if not self._user_stopped:
            try:
                self._audio_queue.put_nowait(audio_data)
            except queue.Full:
                logger.warning("音频队列已满，丢弃最旧的一块数据并尝试重新入队")
                try:
                    self._audio_queue.get_nowait()
                    self._audio_queue.put_nowait(audio_data)
                except queue.Empty:
                    logger.debug("音频队列空了，当前块被忽略")
                except queue.Full:
                    logger.debug("连续丢弃失败，当前块未入队")

    def stop(self, close_connection: bool = True, final_result_timeout: float = 8.0) -> str:
        """停止识别，返回最终结果

        Args:
            close_connection: Whether to close the WebSocket after this session.
            final_result_timeout: Seconds to wait for the server final result.

        Returns:
            识别的文字
        """
        with self._state_lock:
            try:
                self._audio_queue.put_nowait(None)  # 发送结束信号
            except queue.Full:
                try:
                    self._audio_queue.get_nowait()
                except queue.Empty:
                    pass
                self._audio_queue.put_nowait(None)

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._send_end_frame()

        self._user_stopped = True
        self._running = False

        # 等待服务端返回最终结果或连接断开，最多等待8秒
        deadline = time.time() + final_result_timeout
        while time.time() < deadline:
            if self._server_final or not self._connected:
                break
            time.sleep(0.1)

        logger.info(
            "识别会话结束: 结果长度=%s, 音频帧=%s, 音频字节=%s, 服务端消息=%s, 服务端最终=%s",
            len(self._result_text),
            self._audio_frames_sent,
            self._audio_bytes_sent,
            self._messages_received,
            self._server_final,
        )

        if close_connection:
            self.cleanup()

        return self._result_text

    def cleanup(self) -> None:
        """Release WebSocket and sender resources."""
        self._user_stopped = True
        self._running = False

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

        ws = self._ws
        self._ws = None
        if ws:
            try:
                ws.close()
            except Exception as e:
                logger.debug(f"关闭 WebSocket 失败: {e}")

        self._connected = False
        self._thread = None

        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                break

    @property
    def is_running(self) -> bool:
        """是否正在识别"""
        return self._running


class XunfeiRecognizer:
    """讯飞短语音识别（非流式）- 用于简单场景"""

    def __init__(
        self,
        app_id: str,
        api_key: str,
        api_secret: str,
        language: str = "zh_cn",
    ):
        self.app_id = app_id
        self.api_key = api_key
        self.api_secret = api_secret
        self.language = language

    def transcribe(self, audio_data: bytes) -> str:
        """识别音频数据

        Args:
            audio_data: PCM音频数据

        Returns:
            识别的文字
        """
        result_text = ""
        error_msg = ""

        def on_result(text, is_final):
            nonlocal result_text
            result_text = text

        def on_error(ws, error):
            nonlocal error_msg
            error_msg = str(error)

        streamer = XunfeiStreamer(
            app_id=self.app_id,
            api_key=self.api_key,
            api_secret=self.api_secret,
            language=self.language,
            on_result=on_result,
        )

        if streamer.start():
            streamer.send_audio(audio_data)
            result_text = streamer.stop()

        return result_text

    def is_available(self) -> bool:
        """检查配置是否完整"""
        return bool(self.app_id and self.api_key and self.api_secret)

    @property
    def name(self) -> str:
        return "xunfei"
