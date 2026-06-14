"""Abstract base class for speech recognizers."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO


class Recognizer(ABC):
    """Abstract base class for speech recognition backends."""

    @abstractmethod
    def transcribe(self, audio_data: bytes | Path | BinaryIO) -> str:
        """Transcribe audio data to text.

        Args:
            audio_data: Audio data as bytes, file path, or file-like object.

        Returns:
            Transcribed text.
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the recognizer is properly configured and available.

        Returns:
            True if the recognizer can be used, False otherwise.
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the name of this recognizer backend."""
        pass
