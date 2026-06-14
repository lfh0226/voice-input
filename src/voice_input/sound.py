"""音效反馈模块 - 录音状态提示音"""

import logging
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# 尝试导入sounddevice
try:
    import sounddevice as sd

    SD_AVAILABLE = True
except ImportError:
    SD_AVAILABLE = False
    logger.warning("sounddevice未安装，音效反馈不可用")


class SoundFeedback:
    """录音状态音效反馈

    使用合成提示音，无需外部音频文件
    """

    def __init__(self, enabled: bool = True, sample_rate: int = 44100):
        """初始化音效反馈

        Args:
            enabled: 是否启用音效
            sample_rate: 音频采样率
        """
        self.enabled = enabled and SD_AVAILABLE
        self.sample_rate = sample_rate

        # 预生成提示音
        self._start_beep: Optional[np.ndarray] = None
        self._end_beep: Optional[np.ndarray] = None
        self._error_beep: Optional[np.ndarray] = None

        if self.enabled:
            self._generate_sounds()

    def _generate_sounds(self):
        """预生成所有提示音"""
        # 开始录音: 高音短促 (880Hz, 100ms)
        self._start_beep = self._generate_beep(880, 0.08, 0.3)

        # 结束录音: 低音短促 (440Hz, 100ms)
        self._end_beep = self._generate_beep(440, 0.08, 0.3)

        # 错误提示: 双音 (先高后低)
        self._error_beep = self._generate_error_sound()

    def _generate_beep(self, frequency: int, duration: float, volume: float) -> np.ndarray:
        """生成单音提示音

        Args:
            frequency: 频率 (Hz)
            duration: 时长 (秒)
            volume: 音量 (0.0-1.0)

        Returns:
            音频数据 (float32)
        """
        t = np.linspace(0, duration, int(self.sample_rate * duration))

        # 正弦波
        beep = np.sin(2 * np.pi * frequency * t) * volume

        # 淡入淡出 (避免爆音)
        fade_samples = int(0.01 * self.sample_rate)  # 10ms淡入淡出
        if len(beep) > 2 * fade_samples:
            fade_in = np.linspace(0, 1, fade_samples)
            fade_out = np.linspace(1, 0, fade_samples)
            beep[:fade_samples] *= fade_in
            beep[-fade_samples:] *= fade_out

        return beep.astype(np.float32)

    def _generate_error_sound(self) -> np.ndarray:
        """生成错误提示音 (双音)"""
        # 两个不同频率的音
        beep1 = self._generate_beep(600, 0.1, 0.3)
        beep2 = self._generate_beep(400, 0.15, 0.3)

        # 中间间隔
        silence = np.zeros(int(0.05 * self.sample_rate), dtype=np.float32)

        return np.concatenate([beep1, silence, beep2])

    def _play(self, audio: np.ndarray):
        """播放音频 (非阻塞)

        Args:
            audio: 音频数据
        """
        if not self.enabled or audio is None:
            return

        try:
            sd.play(audio, self.sample_rate)
        except Exception as e:
            logger.debug(f"播放音效失败: {e}")

    def play_start(self):
        """播放开始录音提示音"""
        if self.enabled:
            logger.debug("播放开始提示音")
            self._play(self._start_beep)

    def play_end(self):
        """播放结束录音提示音"""
        if self.enabled:
            logger.debug("播放结束提示音")
            self._play(self._end_beep)

    def play_error(self):
        """播放错误提示音"""
        if self.enabled:
            logger.debug("播放错误提示音")
            self._play(self._error_beep)

    def is_available(self) -> bool:
        """检查音效是否可用"""
        return self.enabled and SD_AVAILABLE


class FileSoundFeedback:
    """基于文件的音效反馈

    从文件加载提示音，支持自定义音效
    """

    def __init__(
        self,
        enabled: bool = True,
        start_sound: Optional[Path] = None,
        end_sound: Optional[Path] = None,
        error_sound: Optional[Path] = None,
    ):
        """初始化文件音效反馈

        Args:
            enabled: 是否启用
            start_sound: 开始录音音效文件
            end_sound: 结束录音音效文件
            error_sound: 错误提示音效文件
        """
        self.enabled = enabled and SD_AVAILABLE
        self._start_sound = self._load_sound(start_sound)
        self._end_sound = self._load_sound(end_sound)
        self._error_sound = self._load_sound(error_sound)

    def _load_sound(self, path: Optional[Path]) -> Optional[np.ndarray]:
        """加载音频文件"""
        if not path or not path.exists():
            return None

        try:
            import soundfile as sf

            data, sr = sf.read(str(path), dtype="float32")
            return data
        except ImportError:
            logger.warning("soundfile未安装，无法加载音频文件")
            return None
        except Exception as e:
            logger.warning(f"加载音频文件失败 {path}: {e}")
            return None

    def play_start(self):
        """播放开始提示音"""
        if self.enabled and self._start_sound is not None:
            sd.play(self._start_sound)

    def play_end(self):
        """播放结束提示音"""
        if self.enabled and self._end_sound is not None:
            sd.play(self._end_sound)

    def play_error(self):
        """播放错误提示音"""
        if self.enabled and self._error_sound is not None:
            sd.play(self._error_sound)
