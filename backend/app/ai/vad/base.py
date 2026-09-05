from abc import ABC, abstractmethod
from typing import Optional

class VADProvider(ABC):
    """
    Abstract interface for Voice Activity Detection (VAD).
    Identifies speech activity and utterance boundaries.
    """

    @abstractmethod
    async def is_speech(self, audio_chunk: bytes, sample_rate: int = 16000) -> bool:
        """
        Determines whether a single audio chunk contains speech.
        Expects 16-bit mono PCM audio.
        """
        pass

    @abstractmethod
    async def process_stream(
        self, session_id: str, audio_chunk: bytes, sample_rate: int = 16000
    ) -> Optional[bytes]:
        """
        Buffers incoming streaming chunks for a session.
        When speech has occurred and subsequent silence reaches the threshold (utterance boundary),
        returns the accumulated speech audio (in 16-bit mono PCM bytes).
        Otherwise returns None.
        """
        pass

    @abstractmethod
    async def reset(self, session_id: str) -> None:
        """Resets the accumulated stream buffer and state for this session."""
        pass
