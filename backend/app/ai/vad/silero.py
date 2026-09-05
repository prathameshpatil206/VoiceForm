import asyncio
import logging
from typing import Dict, List, Optional
import numpy as np

from app.ai.vad.base import VADProvider
from app.config import config

logger = logging.getLogger("voiceform.vad.silero")

class SessionVADState:
    def __init__(self) -> None:
        self.has_speech: bool = False
        self.accumulated_chunks: List[bytes] = []
        self.pre_buffer: List[bytes] = []
        self.consecutive_silence_frames: int = 0
        self.total_speech_frames: int = 0

    def reset(self) -> None:
        self.has_speech = False
        self.accumulated_chunks.clear()
        self.pre_buffer.clear()
        self.consecutive_silence_frames = 0
        self.total_speech_frames = 0

class SileroVADProvider(VADProvider):
    """
    Real Silero VAD implementation using ONNX Runtime for low-latency voice activity detection.
    Segments continuous incoming audio stream into bounded speech utterances.
    """

    def __init__(
        self,
        threshold: float = config.VAD_THRESHOLD,
        silence_duration_ms: int = config.VAD_SILENCE_DURATION_MS
    ) -> None:
        self.threshold = threshold
        self.silence_duration_ms = silence_duration_ms
        self._sessions: Dict[str, SessionVADState] = {}
        self._lock = asyncio.Lock()
        self._model = None
        self._initialized = False

    def _ensure_model(self) -> None:
        if self._initialized:
            return
        try:
            from silero_vad import load_silero_vad
            self._model = load_silero_vad(onnx=True)
            self._initialized = True
            logger.info("✅ Silero VAD loaded successfully via ONNX runtime")
        except Exception as e:
            logger.warning(f"Could not load silero_vad with onnx=True, attempting fallback: {e}")
            try:
                from silero_vad import load_silero_vad
                self._model = load_silero_vad(onnx=False)
                self._initialized = True
                logger.info("✅ Silero VAD loaded successfully via PyTorch fallback")
            except Exception as e2:
                logger.error(f"Failed to load Silero VAD model: {e2}")
                raise

    def _bytes_to_float32(self, pcm_bytes: bytes) -> np.ndarray:
        """Convert 16-bit mono PCM bytes to normalized float32 numpy array [-1.0, 1.0]."""
        audio_int16 = np.frombuffer(pcm_bytes, dtype=np.int16)
        return audio_int16.astype(np.float32) / 32768.0

    async def is_speech(self, audio_chunk: bytes, sample_rate: int = 16000) -> bool:
        """
        Check if an audio chunk contains speech.
        Returns True if any 512-sample frame exceeds speech threshold.
        """
        self._ensure_model()
        if len(audio_chunk) < 1024:  # At least 512 samples (16-bit = 2 bytes/sample)
            return False

        samples = self._bytes_to_float32(audio_chunk)
        frame_size = 512
        num_frames = len(samples) // frame_size

        for i in range(num_frames):
            frame = samples[i * frame_size : (i + 1) * frame_size]
            prob = self._predict_frame(frame, sample_rate)
            if prob >= self.threshold:
                return True
        return False

    def _predict_frame(self, frame: np.ndarray, sample_rate: int) -> float:
        import torch
        tensor = torch.from_numpy(frame).unsqueeze(0)
        assert self._model is not None, "Silero VAD model is not loaded"
        with torch.no_grad():
            output = self._model(tensor, sample_rate)
            if isinstance(output, torch.Tensor):
                return float(output.item())
            return float(output)

    async def process_stream(
        self, session_id: str, audio_chunk: bytes, sample_rate: int = 16000
    ) -> Optional[bytes]:
        """
        Processes streaming audio chunks and detects speech boundaries.
        Returns complete speech utterance bytes once silence duration threshold is met.
        """
        self._ensure_model()

        async with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = SessionVADState()
            state = self._sessions[session_id]

        if len(audio_chunk) == 0:
            return None

        samples = self._bytes_to_float32(audio_chunk)
        frame_size = 512  # 32ms at 16kHz
        num_frames = len(samples) // frame_size
        max_silence_frames = max(3, int(self.silence_duration_ms / 32.0))

        utterance_complete = False

        for i in range(num_frames):
            frame = samples[i * frame_size : (i + 1) * frame_size]
            prob = self._predict_frame(frame, sample_rate)
            frame_bytes = audio_chunk[i * frame_size * 2 : (i + 1) * frame_size * 2]

            if prob >= self.threshold:
                # Speech frame detected
                if not state.has_speech:
                    state.has_speech = True
                    # Prepend small pre-buffer (up to 200ms) to capture initial phoneme
                    state.accumulated_chunks.extend(state.pre_buffer)
                    state.pre_buffer.clear()
                state.accumulated_chunks.append(frame_bytes)
                state.consecutive_silence_frames = 0
                state.total_speech_frames += 1
            else:
                # Silence frame detected
                if state.has_speech:
                    state.accumulated_chunks.append(frame_bytes)
                    state.consecutive_silence_frames += 1
                    if state.consecutive_silence_frames >= max_silence_frames:
                        utterance_complete = True
                        break
                else:
                    # Rolling pre-buffer before speech starts (keep ~6 frames = ~192ms)
                    state.pre_buffer.append(frame_bytes)
                    if len(state.pre_buffer) > 6:
                        state.pre_buffer.pop(0)

        if utterance_complete and state.total_speech_frames >= 4:
            # Utterance successfully completed with at least 128ms of speech
            complete_utterance = b"".join(state.accumulated_chunks)
            state.reset()
            logger.info(
                f"🎙️ Utterance detected for session={session_id}: "
                f"{len(complete_utterance)} bytes ({len(complete_utterance) / 32000:.2f}s)"
            )
            return complete_utterance
        elif utterance_complete:
            # False alarm (too brief)
            state.reset()
            return None

        return None

    async def reset(self, session_id: str) -> None:
        async with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id].reset()
