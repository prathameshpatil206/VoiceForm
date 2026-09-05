import asyncio
import logging
from typing import AsyncIterator, Dict, Optional
import httpx

from app.ai.tts.base import (
    TTSAPIError,
    TTSAuthenticationError,
    TTSCancelledError,
    TTSChunk,
    TTSNetworkError,
    TTSProvider,
)
from app.config import config

logger = logging.getLogger("voiceform.tts.rime")


class RimeTTSProvider(TTSProvider):
    """
    Production TTS Provider for Rime Text-to-Speech API.
    Streams audio directly via HTTP streaming to minimize time-to-first-audio.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        speaker: Optional[str] = None,
        model_id: Optional[str] = None,
        audio_format: Optional[str] = None,
        sampling_rate: Optional[int] = None,
        timeout_seconds: Optional[float] = None
    ) -> None:
        self.api_key = api_key if api_key is not None else config.RIME_API_KEY
        self.base_url = (base_url or config.RIME_BASE_URL).rstrip("/")
        self.speaker = speaker or config.RIME_SPEAKER
        self.model_id = model_id or config.RIME_MODEL_ID
        self.audio_format = audio_format or config.RIME_AUDIO_FORMAT
        self.sampling_rate = sampling_rate or config.RIME_SAMPLING_RATE
        self.timeout_seconds = timeout_seconds or config.TTS_TIMEOUT

        # Track active request cancellations
        self._cancel_events: Dict[str, asyncio.Event] = {}
        self._lock = asyncio.Lock()

    def is_configured(self) -> bool:
        """Returns True if Rime API credentials are provided."""
        return bool(self.api_key and self.api_key.strip())

    async def cancel(self, request_id: str) -> None:
        """Signals cancellation for an in-flight synthesis request."""
        async with self._lock:
            event = self._cancel_events.get(request_id)
            if event:
                event.set()
                logger.info(f"Cancellation signal registered for Rime request_id={request_id}")

    async def synthesize_stream(
        self,
        text: str,
        session_id: Optional[str] = None,
        request_id: Optional[str] = None,
        speaker: Optional[str] = None,
        **kwargs
    ) -> AsyncIterator[TTSChunk]:
        """
        Streams synthesized audio chunks from Rime TTS API for the given text.
        """
        if not self.is_configured():
            raise TTSAuthenticationError(
                message="RIME_API_KEY is not set. Please set RIME_API_KEY environment variable.",
                details="Missing credentials"
            )

        cleaned_text = text.strip()
        if not cleaned_text:
            return

        req_id = request_id or f"tts_{asyncio.get_event_loop().time()}"
        cancel_event = asyncio.Event()

        async with self._lock:
            self._cancel_events[req_id] = cancel_event

        # Resolve format header
        fmt = self.audio_format.lower()
        if fmt == "pcm":
            accept_header = "audio/pcm"
        elif fmt == "mp3":
            accept_header = "audio/mpeg"
        elif fmt == "wav":
            accept_header = "audio/wav"
        else:
            accept_header = "audio/pcm"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": accept_header
        }

        chosen_speaker = speaker or self.speaker
        payload = {
            "text": cleaned_text,
            "speaker": chosen_speaker,
            "modelId": self.model_id,
            "samplingRate": self.sampling_rate
        }

        # Include additional kwargs if supported (e.g. speed / timeScaleFactor)
        if "speed" in kwargs and kwargs["speed"] is not None:
            payload["speedAlpha"] = kwargs["speed"]
        if "timeScaleFactor" in kwargs and kwargs["timeScaleFactor"] is not None:
            payload["timeScaleFactor"] = kwargs["timeScaleFactor"]

        logger.info(
            f"Synthesizing Rime TTS for req_id={req_id} model={self.model_id} speaker={chosen_speaker} "
            f"format={fmt} text='{cleaned_text[:40]}...'"
        )

        chunk_index = 0
        received_bytes = 0

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                async with client.stream(
                    "POST",
                    self.base_url,
                    headers=headers,
                    json=payload
                ) as response:
                    # Check for authentication errors
                    if response.status_code in (401, 403):
                        error_body = (await response.aread()).decode(errors="replace")
                        raise TTSAuthenticationError(
                            message=f"Rime API authentication rejected with status {response.status_code}",
                            details=error_body
                        )

                    # Check for client or server errors
                    if response.status_code >= 400:
                        error_body = (await response.aread()).decode(errors="replace")
                        raise TTSAPIError(
                            message=f"Rime API error {response.status_code}: {error_body}",
                            status_code=response.status_code,
                            details=error_body
                        )

                    # Stream binary chunks as they arrive from Rime
                    async for raw_chunk in response.aiter_bytes(chunk_size=2048):
                        # Check if cancellation was requested
                        if cancel_event.is_set():
                            logger.info(f"Rime TTS synthesis cancelled for req_id={req_id}")
                            raise TTSCancelledError(f"Rime TTS request {req_id} was cancelled.")

                        if not raw_chunk:
                            continue

                        received_bytes += len(raw_chunk)
                        yield TTSChunk(
                            audio_bytes=raw_chunk,
                            chunk_index=chunk_index,
                            format=fmt,
                            sample_rate=self.sampling_rate,
                            is_final=False,
                            request_id=req_id
                        )
                        chunk_index += 1

            # Emit final empty or delimiter chunk indicating stream completion
            yield TTSChunk(
                audio_bytes=b"",
                chunk_index=chunk_index,
                format=fmt,
                sample_rate=self.sampling_rate,
                is_final=True,
                request_id=req_id
            )
            logger.info(f"Finished Rime TTS stream req_id={req_id} total_bytes={received_bytes} chunks={chunk_index}")

        except httpx.ConnectError as e:
            logger.error(f"Network error connecting to Rime API at {self.base_url}: {e}")
            raise TTSNetworkError(
                message=f"Could not connect to Rime API at {self.base_url}",
                details=str(e)
            ) from e
        except httpx.TimeoutException as e:
            logger.error(f"Timeout during Rime TTS stream req_id={req_id}: {e}")
            raise TTSNetworkError(
                message=f"Rime TTS stream timed out after {self.timeout_seconds}s",
                details=str(e)
            ) from e
        except (TTSAuthenticationError, TTSAPIError, TTSCancelledError):
            raise
        except Exception as e:
            logger.error(f"Unexpected error during Rime TTS stream: {e}")
            raise TTSAPIError(
                message=f"Unexpected Rime TTS error: {str(e)}",
                details=str(e)
            ) from e
        finally:
            async with self._lock:
                self._cancel_events.pop(req_id, None)
