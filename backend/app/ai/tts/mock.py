import asyncio
import math
from typing import AsyncIterator, Dict, Optional
import numpy as np

from app.ai.tts.base import (
    TTSAPIError,
    TTSAuthenticationError,
    TTSCancelledError,
    TTSChunk,
    TTSProvider,
)


class MockTTSProvider(TTSProvider):
    """
    Mock TTS Provider for local automated testing and environments without Rime credentials.
    Generates synthetic 16kHz linear PCM audio chunks with realistic streaming behavior.
    """

    def __init__(
        self,
        format: str = "pcm",
        sample_rate: int = 16000,
        chunk_duration_ms: int = 100,
        total_chunks: int = 4,
        simulate_network_delay: bool = True,
        simulate_error: Optional[str] = None
    ) -> None:
        self.format = format
        self.sample_rate = sample_rate
        self.chunk_duration_ms = chunk_duration_ms
        self.total_chunks = total_chunks
        self.simulate_network_delay = simulate_network_delay
        self.simulate_error = simulate_error

        self._cancelled_requests: set[str] = set()
        self._lock = asyncio.Lock()

    async def cancel(self, request_id: str) -> None:
        async with self._lock:
            self._cancelled_requests.add(request_id)

    async def synthesize_stream(
        self,
        text: str,
        session_id: Optional[str] = None,
        request_id: Optional[str] = None,
        speaker: Optional[str] = None,
        **kwargs
    ) -> AsyncIterator[TTSChunk]:
        req_id = request_id or f"mock_tts_{asyncio.get_event_loop().time()}"

        if self.simulate_error == "AUTH_ERROR":
            raise TTSAuthenticationError("Mock API key invalid or expired")
        elif self.simulate_error == "API_ERROR":
            raise TTSAPIError("Mock TTS server 500 internal error", status_code=500)
        elif self.simulate_error == "NETWORK_ERROR":
            raise TTSAPIError("Mock network unreachable")

        # Number of samples per chunk
        chunk_samples = int(self.sample_rate * (self.chunk_duration_ms / 1000.0))
        # Frequency based on text length to vary mock audio
        freq = 440 + (len(text) % 10) * 20

        for i in range(self.total_chunks):
            async with self._lock:
                if req_id in self._cancelled_requests:
                    raise TTSCancelledError(f"Mock TTS request {req_id} was cancelled.")

            if self.simulate_network_delay:
                await asyncio.sleep(0.02)

            async with self._lock:
                if req_id in self._cancelled_requests:
                    raise TTSCancelledError(f"Mock TTS request {req_id} was cancelled.")

            # Synthesize tone samples (16-bit signed PCM little-endian)
            t = np.linspace(
                (i * self.chunk_duration_ms) / 1000.0,
                ((i + 1) * self.chunk_duration_ms) / 1000.0,
                chunk_samples,
                endpoint=False
            )
            sine_wave = (0.2 * np.sin(2 * math.pi * freq * t) * 32767).astype(np.int16)
            pcm_bytes = sine_wave.tobytes()

            yield TTSChunk(
                audio_bytes=pcm_bytes,
                chunk_index=i,
                format=self.format,
                sample_rate=self.sample_rate,
                is_final=False,
                request_id=req_id
            )

        # Final delimiter chunk
        yield TTSChunk(
            audio_bytes=b"",
            chunk_index=self.total_chunks,
            format=self.format,
            sample_rate=self.sample_rate,
            is_final=True,
            request_id=req_id
        )
