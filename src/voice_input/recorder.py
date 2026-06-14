"""Audio recording module - 支持流式录音和批量录音"""

import logging
import tempfile
import threading
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import sounddevice as sd

logger = logging.getLogger(__name__)


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
    ):
        """初始化流式录音器

        Args:
            sample_rate: 采样率 (Hz)
            channels: 声道数
            chunk_ms: 每块音频时长 (毫秒)
            on_chunk: 音频块回调函数，接收PCM字节
        """
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_ms = chunk_ms
        self.on_chunk = on_chunk
        self._retain_audio = retain_audio

        # 计算每块采样数 (40ms @ 16kHz = 640 samples)
        self.chunk_size = int(sample_rate * chunk_ms / 1000)

        self._is_recording = False
        self._stream: Optional[sd.InputStream] = None
        self._audio_buffer: list[np.ndarray] = []
        self._lock = threading.Lock()

    @property
    def is_recording(self) -> bool:
        """是否正在录音"""
        return self._is_recording

    def _audio_callback(
        self, indata: np.ndarray, frames: int, time_info: dict, status: sd.CallbackFlags
    ) -> None:
        """音频回调 - 实时输出PCM数据"""
        if not self._is_recording:
            return

        if self._retain_audio:
            with self._lock:
                self._audio_buffer.append(indata.copy())

        # 转换为PCM字节并发送
        if self.on_chunk:
            # float32 -> int16 -> bytes
            pcm_data = (indata[:, 0] * 32767).astype(np.int16).tobytes()
            self.on_chunk(pcm_data)

    def start(self) -> bool:
        """开始流式录音

        Returns:
            是否成功启动
        """
        if self._is_recording:
            logger.warning("已在录音中")
            return False

        logger.info(f"开始流式录音: {self.sample_rate}Hz, 块大小{self.chunk_ms}ms")

        if self._retain_audio:
            with self._lock:
                self._audio_buffer = []

        self._is_recording = True

        try:
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype=np.float32,
                blocksize=self.chunk_size,
                callback=self._audio_callback,
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
