from abc import ABC, abstractmethod
from typing import Optional
from pydantic import BaseModel

class TranscriptResult(BaseModel):
    """
    Structured transcription output from an ASR provider.
    """
    text: str
    language: Optional[str] = "en"
    confidence: Optional[float] = None
    duration_seconds: Optional[float] = None

class ASRProvider(ABC):
    """
    Abstract interface for Automatic Speech Recognition (ASR).
    Converts speech audio into structured transcripts.
    """

    @abstractmethod
    async def transcribe(
        self, audio_data: bytes, sample_rate: int = 16000
    ) -> TranscriptResult:
        """
        Transcribes audio data (16-bit mono PCM or WAV bytes).
        Returns a structured TranscriptResult.
        """
        pass
