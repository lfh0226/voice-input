"""Whisper speech recognition backend."""

import logging
from pathlib import Path
from typing import BinaryIO

import numpy as np

from voice_input.recognizer.base import Recognizer

logger = logging.getLogger(__name__)


class WhisperRecognizer(Recognizer):
    """Speech recognition using OpenAI Whisper."""

    def __init__(
        self,
        model: str = "small",
        language: str | None = "zh",
        device: str = "auto",
    ):
        """Initialize Whisper recognizer.

        Args:
            model: Whisper model size (tiny, base, small, medium, large).
            language: Language code for transcription. None for auto-detect.
            device: Device to use (auto, cuda, cpu).
        """
        self.model_name = model
        self.language = language
        self.device = device
        self._model = None
        self._available = None

    def _load_model(self):
        """Lazy load the Whisper model."""
        if self._model is None:
            import whisper

            logger.info(f"Loading Whisper model: {self.model_name}")

            # Determine device
            if self.device == "auto":
                import torch

                device = "cuda" if torch.cuda.is_available() else "cpu"
            else:
                device = self.device

            logger.info(f"Using device: {device}")
            self._model = whisper.load_model(self.model_name, device=device)
            logger.info("Whisper model loaded successfully")

        return self._model

    def transcribe(self, audio_data: bytes | Path | BinaryIO | np.ndarray) -> str:
        """Transcribe audio data to text.

        Args:
            audio_data: Audio data as bytes, file path, file-like object, or numpy array.

        Returns:
            Transcribed text.
        """
        model = self._load_model()

        # Handle different input types
        if isinstance(audio_data, np.ndarray):
            # Numpy array - use directly
            audio = audio_data.squeeze()
        elif isinstance(audio_data, Path):
            # File path
            audio = str(audio_data)
        elif isinstance(audio_data, bytes):
            # Bytes - write to temp file
            import tempfile

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(audio_data)
                temp_path = f.name
            audio = temp_path
        elif hasattr(audio_data, "read"):
            # File-like object
            content = audio_data.read()
            if isinstance(content, str):
                content = content.encode()
            import tempfile

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(content)
                temp_path = f.name
            audio = temp_path
        else:
            raise ValueError(f"Unsupported audio data type: {type(audio_data)}")

        # Transcribe
        kwargs = {}
        if self.language:
            kwargs["language"] = self.language

        result = model.transcribe(audio, **kwargs)
        text = result["text"].strip()

        logger.debug("Transcribed text length: %s", len(text))
        return text

    def is_available(self) -> bool:
        """Check if Whisper is available."""
        if self._available is None:
            try:
                import whisper  # noqa: F401

                self._available = True
            except ImportError:
                self._available = False
        return self._available

    @property
    def name(self) -> str:
        """Return the name of this recognizer backend."""
        return f"whisper-{self.model_name}"
