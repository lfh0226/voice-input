"""Audio recording module - 支持流式录音和批量录音"""

import logging
import tempfile
import threading
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import sounddevice as sd

logger = logging.getLogger(__name__)

# 讯飞流式识别（audio/L16;rate=16000）要求 16kHz 单声道 PCM
TARGET_SAMPLE_RATE = 16000
# 设备不支持目标采样率时的候选采样率（裸 ALSA hw 设备通常只支持 48kHz）
FALLBACK_SAMPLE_RATES = (48000, 44100, 32000, 22050)


def resample_audio(audio: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    """将一维音频重采样到目标采样率（仅依赖 numpy）。

    降采样且为整数倍时使用块平均（等效简单低通滤波），否则使用线性插值。

    Args:
        audio: 一维音频数据
        src_rate: 原始采样率 (Hz)
        dst_rate: 目标采样率 (Hz)

    Returns:
        重采样后的音频数据
    """
    if src_rate == dst_rate or audio.size == 0:
        return audio

    dst_size = int(round(audio.size * dst_rate / src_rate))
    if dst_size <= 0:
        return audio[:0]

    if dst_rate < src_rate:
        factor = src_rate / dst_rate
        window = int(round(factor))
        if window > 1 and abs(factor - window) < 1e-9:
            usable = audio.size - audio.size % window
            if usable == 0:
                return audio[:0]
            return audio[:usable].reshape(-1, window).mean(axis=1).astype(audio.dtype)

    x_src = np.linspace(0.0, 1.0, num=audio.size, endpoint=False)
    x_dst = np.linspace(0.0, 1.0, num=dst_size, endpoint=False)
    return np.interp(x_dst, x_src, audio).astype(audio.dtype)


class AudioRecorder:
    """Audio recorder using sounddevice."""

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        max_duration: float = 60.0,
        on_start: Callable[[], None] | None = None,
        on_stop: Callable[[], None] | None = None,
    ):
        """Initialize audio recorder.

        Args:
            sample_rate: Audio sample rate in Hz.
            channels: Number of audio channels.
            max_duration: Maximum recording duration in seconds.
            on_start: Callback when recording starts.
            on_stop: Callback when recording stops.
        """
        self.sample_rate = sample_rate
        self.channels = channels
        self.max_duration = max_duration
        self.on_start = on_start
        self.on_stop = on_stop

        self._is_recording = False
        self._audio_data: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._stop_event = threading.Event()

    @property
    def is_recording(self) -> bool:
        """Check if currently recording."""
        return self._is_recording

    def _audio_callback(
        self, indata: np.ndarray, frames: int, time_info: dict, status: sd.CallbackFlags
    ) -> None:
        """Callback for audio stream."""
        if self._is_recording and not self._stop_event.is_set():
            self._audio_data.append(indata.copy())
        else:
            raise sd.CallbackStop()

    def start_recording(self) -> None:
        """Start recording audio."""
        if self._is_recording:
            logger.warning("Already recording, ignoring start request")
            return

        logger.info("Starting audio recording...")
        self._audio_data = []
        self._stop_event.clear()
        self._is_recording = True

        try:
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype=np.float32,
                callback=self._audio_callback,
            )
            self._stream.start()
            logger.info(f"Audio stream started: {self.sample_rate}Hz, {self.channels} channel(s)")

            if self.on_start:
                self.on_start()

            # Start max duration timer
            if self.max_duration > 0:
                threading.Timer(self.max_duration, self.stop_recording).start()
        except Exception as e:
            logger.error(f"Failed to start recording: {e}")
            self._is_recording = False
            raise

    def stop_recording(self) -> np.ndarray | None:
        """Stop recording and return audio data.

        Returns:
            Recorded audio data as numpy array, or None if not recording.
        """
        if not self._is_recording:
            logger.warning("Not recording, ignoring stop request")
            return None

        logger.info("Stopping audio recording...")
        self._is_recording = False
        self._stop_event.set()

        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        if self.on_stop:
            self.on_stop()

        if not self._audio_data:
            logger.warning("No audio data recorded")
            return None

        # Concatenate all audio chunks
        audio = np.concatenate(self._audio_data, axis=0)
        logger.info(f"Recorded {len(audio)} samples ({len(audio)/self.sample_rate:.2f} seconds)")
        return audio

    def save_to_file(self, audio: np.ndarray, filepath: Path | None = None) -> Path:
        """Save audio data to a WAV file.

        Args:
            audio: Audio data as numpy array.
            filepath: Output file path. If None, creates a temp file.

        Returns:
            Path to the saved file.
        """
        import wave

        if filepath is None:
            temp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            temp_file.close()
            filepath = Path(temp_file.name)

        # Convert float32 to int16
        audio_int16 = (audio * 32767).astype(np.int16)

        with wave.open(str(filepath), "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(self.sample_rate)
            wf.writeframes(audio_int16.tobytes())

        return filepath

    def get_audio_bytes(self, audio: np.ndarray) -> bytes:
        """Convert audio data to WAV bytes.

        Args:
            audio: Audio data as numpy array.

        Returns:
            Audio data as WAV-formatted bytes.
        """
        import io
        import wave

        buffer = io.BytesIO()
        audio_int16 = (audio * 32767).astype(np.int16)

        with wave.open(buffer, "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(audio_int16.tobytes())

        return buffer.getvalue()

    @staticmethod
    def list_devices() -> list[dict]:
        """List available audio input devices.

        Returns:
            List of device info dictionaries.
        """
        devices = sd.query_devices()
        input_devices = []
        for i, dev in enumerate(devices):
            if dev["max_input_channels"] > 0:
                input_devices.append(
                    {
                        "index": i,
                        "name": dev["name"],
                        "channels": dev["max_input_channels"],
                        "sample_rate": dev["default_samplerate"],
                    }
                )
        return input_devices


class StreamingRecorder:
    """流式录音器 - 实时输出音频块，用于流式语音识别"""

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        chunk_ms: int = 40,
        on_chunk: Optional[Callable[[bytes], None]] = None,
        retain_audio: bool = False,
        device: int | str | None = None,
    ):
        """初始化流式录音器

        Args:
            sample_rate: 采样率 (Hz)
            channels: 声道数
            chunk_ms: 每块音频时长 (毫秒)
            on_chunk: 音频块回调函数，接收PCM字节
            retain_audio: 是否保留完整音频
            device: 指定输入设备（索引或名称），None 表示使用系统默认设备
        """
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_ms = chunk_ms
        self.on_chunk = on_chunk
        self._retain_audio = retain_audio
        self.device = device

        # 计算每块采样数 (40ms @ 16kHz = 640 samples)
        self.chunk_size = int(sample_rate * chunk_ms / 1000)

        self._is_recording = False
        self._stream: Optional[sd.InputStream] = None
        self._audio_buffer: list[np.ndarray] = []
        self._lock = threading.Lock()
        # 实际打开的采样率/声道数，可能与请求值不同（设备能力限制）
        self._stream_sample_rate = sample_rate
        self._stream_channels = channels

    @property
    def is_recording(self) -> bool:
        """是否正在录音"""
        return self._is_recording

    @staticmethod
    def probe(
        device: int | str | None = None, sample_rate: int = TARGET_SAMPLE_RATE
    ) -> tuple[bool, str]:
        """检查音频输入链路是否可用（启动自检用）。

        Returns:
            (是否可用, 说明信息)
        """
        try:
            info = sd.query_devices(device, kind="input")
        except Exception as exc:
            return False, f"没有可用的录音设备: {exc}"

        index = info.get("index", device)
        name = info.get("name", "unknown")
        try:
            sd.check_input_settings(
                device=index, samplerate=sample_rate, channels=1, dtype="float32"
            )
        except Exception as exc:
            return False, (
                f"设备 {index} ({name}) 不支持 {sample_rate}Hz 录音: {exc}\n"
                "   常见原因：程序不在桌面会话环境内运行（缺少 XDG_RUNTIME_DIR/PULSE_SERVER），"
                "PortAudio 会退回到裸 ALSA 硬件设备。"
            )
        return True, f"设备 {index} ({name}) @ {sample_rate}Hz"

    def _select_input_params(self) -> tuple[int, int]:
        """选择设备实际支持的 (采样率, 声道数)。

        部分设备（如裸 ALSA hw 设备）只支持固定采样率（常见 48kHz），
        此时退回到设备支持的采样率，采集后再重采样到目标采样率。

        如果无法预校验（例如设备信息不可用），返回请求参数，由实际打开时决定。
        """
        rates: list[int] = []
        for rate in (self.sample_rate, *FALLBACK_SAMPLE_RATES):
            if rate not in rates:
                rates.append(rate)

        channel_options = [self.channels] if self.channels == 1 else [self.channels, 1]

        last_error: Exception | None = None
        for channels in channel_options:
            for rate in rates:
                try:
                    sd.check_input_settings(
                        device=self.device,
                        samplerate=rate,
                        channels=channels,
                        dtype="float32",
                    )
                    return rate, channels
                except Exception as exc:
                    last_error = exc

        logger.debug(
            "无法预校验录音参数（%s），按请求参数 %dHz/%d声道 尝试",
            last_error,
            self.sample_rate,
            self.channels,
        )
        return self.sample_rate, self.channels

    def _prepare_audio(self, indata: np.ndarray) -> np.ndarray:
        """把设备原始采集数据转换为目标采样率的单声道数据。"""
        if indata.ndim == 1:
            data = indata
        elif indata.shape[1] > 1:
            data = indata.mean(axis=1)
        else:
            data = indata[:, 0]

        if self._stream_sample_rate != self.sample_rate:
            data = resample_audio(data, self._stream_sample_rate, self.sample_rate)
        return data

    def _audio_callback(
        self, indata: np.ndarray, frames: int, time_info: dict, status: sd.CallbackFlags
    ) -> None:
        """音频回调 - 实时输出PCM数据"""
        if not self._is_recording:
            return

        data = self._prepare_audio(indata)

        if self._retain_audio:
            with self._lock:
                self._audio_buffer.append(data.copy())

        # 转换为PCM字节并发送
        if self.on_chunk:
            # float32 -> int16 -> bytes
            pcm_data = (data * 32767).astype(np.int16).tobytes()
            self.on_chunk(pcm_data)

    def start(self) -> bool:
        """开始流式录音

        Returns:
            是否成功启动
        """
        if self._is_recording:
            logger.warning("已在录音中")
            return False

        if self._retain_audio:
            with self._lock:
                self._audio_buffer = []

        try:
            rate, channels = self._select_input_params()
        except Exception as exc:
            logger.error(f"启动流式录音失败: {exc}")
            return False

        self._stream_sample_rate = rate
        self._stream_channels = channels
        self.chunk_size = max(1, int(rate * self.chunk_ms / 1000))

        if rate != self.sample_rate or channels != self.channels:
            resample_note = (
                f"，并重采样到 {self.sample_rate / 1000:.1f}kHz"
                if rate != self.sample_rate
                else ""
            )
            logger.warning(
                "录音设备不支持 %dHz/%d声道，改用 %dHz/%d声道采集%s",
                self.sample_rate,
                self.channels,
                rate,
                channels,
                resample_note,
            )

        logger.info(f"开始流式录音: {rate}Hz, 块大小{self.chunk_ms}ms")

        self._is_recording = True

        try:
            self._stream = sd.InputStream(
                samplerate=rate,
                channels=channels,
                dtype=np.float32,
                blocksize=self.chunk_size,
                callback=self._audio_callback,
                device=self.device,
            )
            self._stream.start()
            logger.debug("流式录音已启动")
            return True

        except Exception as e:
            logger.error(f"启动流式录音失败: {e}")
            self._is_recording = False
            return False

    def stop(self) -> np.ndarray | None:
        """停止录音并返回完整音频数据

        Returns:
            完整的音频数据 (numpy array)，或None
        """
        if not self._is_recording:
            return None

        logger.info("停止流式录音")
        self._is_recording = False

        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        if not self._retain_audio:
            return None

        with self._lock:
            if not self._audio_buffer:
                return None
            audio = np.concatenate(self._audio_buffer, axis=0)
            self._audio_buffer = []

        logger.info(f"录音完成: {len(audio)} 采样 ({len(audio)/self.sample_rate:.2f}秒)")
        return audio

    def get_pcm_bytes(self, audio: np.ndarray) -> bytes:
        """将numpy音频数据转换为PCM字节

        Args:
            audio: 音频数据 (float32)

        Returns:
            PCM字节 (int16)
        """
        return (audio[:, 0] * 32767).astype(np.int16).tobytes()
