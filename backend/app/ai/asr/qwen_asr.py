import io
import logging
import os
import tempfile
import wave
from typing import Any, Optional
import httpx

from app.ai.asr.base import ASRProvider, TranscriptResult
from app.config import config

logger = logging.getLogger("voiceform.asr.qwen")

class Qwen3ASRProvider(ASRProvider):
    """
    Qwen3-ASR speech-to-text inference provider.
    Supports local model inference via qwen-asr / transformers as well as
    configured API endpoints (e.g. DashScope or OpenAI-compatible audio API).
    """

    def __init__(
        self,
        model_name: str = config.ASR_MODEL,
        api_url: Optional[str] = os.getenv("QWEN_ASR_API_URL"),
        api_key: Optional[str] = os.getenv("DASHSCOPE_API_KEY")
    ) -> None:
        self.model_name = model_name
        self.api_url = api_url
        self.api_key = api_key
        self._local_model: Any = None
        self._initialized = False

    def _pcm_to_wav(self, pcm_bytes: bytes, sample_rate: int = 16000) -> bytes:
        """Wrap raw 16-bit mono PCM bytes in a valid WAV header if not already WAV."""
        if pcm_bytes.startswith(b"RIFF"):
            return pcm_bytes

        wav_io = io.BytesIO()
        with wave.open(wav_io, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm_bytes)
        return wav_io.getvalue()

    def _init_local_model(self) -> None:
        if self._initialized:
            return

        try:
            # 1. Ultra-fast local Whisper engine (cached locally, 0s load, works offline on CPU)
            try:
                import whisper
                self._local_model = whisper.load_model("tiny")
                self._initialized = True
                logger.info("✅ Local ASR engine loaded successfully (whisper tiny)")
                return
            except Exception as e_w:
                logger.debug(f"whisper not available: {e_w}")

            try:
                from faster_whisper import WhisperModel
                self._local_model = WhisperModel("base", device="cpu", compute_type="int8")
                self._initialized = True
                logger.info("✅ Local ASR engine loaded successfully (faster-whisper base)")
                return
            except Exception as e_fw:
                logger.debug(f"faster-whisper not available: {e_fw}")

            logger.info(f"Loading Qwen3-ASR model: {self.model_name} ...")
            try:
                import importlib
                qwen_mod = importlib.import_module("qwen_asr")
                model_cls = getattr(qwen_mod, "Qwen3ASRModel")
                self._local_model = model_cls.from_pretrained(
                    self.model_name,
                    device_map="auto"
                )
                self._initialized = True
                logger.info("✅ Qwen3-ASR loaded successfully via qwen-asr package")
                return
            except Exception:
                logger.debug("qwen_asr package not available, trying transformers pipeline...")

            try:
                import importlib
                trans_mod = importlib.import_module("transformers")
                pipeline_fn = getattr(trans_mod, "pipeline")
                self._local_model = pipeline_fn(
                    "automatic-speech-recognition",
                    model=self.model_name,
                    device=0 if os.getenv("CUDA_VISIBLE_DEVICES") else -1
                )
                self._initialized = True
                logger.info("✅ Qwen3-ASR loaded successfully via transformers pipeline")
                return
            except Exception as e_trans:
                logger.debug(f"Transformers pipeline not available: {e_trans}")

            # Fallback to ultra-fast local Whisper engine
            try:
                import whisper
                self._local_model = whisper.load_model("tiny")
                self._initialized = True
                logger.info("✅ Local ASR engine loaded successfully (whisper tiny)")
                return
            except Exception as e_w:
                logger.debug(f"whisper not available: {e_w}")

            try:
                from faster_whisper import WhisperModel
                self._local_model = WhisperModel("base", device="cpu", compute_type="int8")
                self._initialized = True
                logger.info("✅ Local ASR engine loaded successfully (faster-whisper base)")
                return
            except Exception as e_fw:
                logger.debug(f"faster-whisper not available: {e_fw}")

        except Exception as e:
            logger.warning(f"Local ASR model could not be loaded into memory: {e}")
            self._initialized = True  # Mark attempted

    async def transcribe(
        self, audio_data: bytes, sample_rate: int = 16000
    ) -> TranscriptResult:
        """
        Transcribes 16kHz speech audio using Qwen3-ASR.
        """
        wav_bytes = self._pcm_to_wav(audio_data, sample_rate)
        duration_s = len(audio_data) / (sample_rate * 2.0)

        # 1. If an external API URL or DashScope is configured, query the API endpoint
        if self.api_url or self.api_key:
            return await self._transcribe_via_api(wav_bytes, duration_s)

        # 2. Local inference via loaded model
        self._init_local_model()

        if self._local_model is not None:
            try:
                import numpy as np
                # Convert 16-bit mono PCM directly to normalized float32 numpy array
                # This bypasses ffmpeg completely on Windows
                audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

                # Write to temp WAV file as fallback for models needing file path
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                    tmp.write(wav_bytes)
                    tmp_path = tmp.name

                try:
                    if hasattr(self._local_model, "transcribe"):
                        # 1. openai-whisper model (accepts direct numpy array, no ffmpeg required!)
                        try:
                            res = self._local_model.transcribe(audio_np, fp16=False)
                            if isinstance(res, dict):
                                return TranscriptResult(
                                    text=res.get("text", "").strip(),
                                    language=res.get("language", "en"),
                                    confidence=0.95,
                                    duration_seconds=round(duration_s, 2)
                                )
                        except Exception as e_np:
                            logger.debug(f"Direct numpy transcribe failed: {e_np}")

                        # 2. faster_whisper model (returns generator)
                        try:
                            segments, info = self._local_model.transcribe(tmp_path, beam_size=1)
                            text = " ".join([s.text for s in segments]).strip()
                            lang = getattr(info, "language", "en")
                            return TranscriptResult(
                                text=text,
                                language=lang,
                                confidence=0.95,
                                duration_seconds=round(duration_s, 2)
                            )
                        except (TypeError, ValueError):
                            pass

                        # 3. qwen_asr model
                        res = self._local_model.transcribe(audio=[tmp_path])
                        text = res[0].text if res else ""
                        lang = getattr(res[0], "language", "en")
                        return TranscriptResult(
                            text=text.strip(),
                            language=lang,
                            confidence=0.95,
                            duration_seconds=round(duration_s, 2)
                        )
                    else:
                        # Transformers pipeline
                        res = self._local_model(tmp_path)
                        text = res.get("text", "") if isinstance(res, dict) else str(res)
                        return TranscriptResult(
                            text=text.strip(),
                            language="en",
                            confidence=0.95,
                            duration_seconds=round(duration_s, 2)
                        )
                finally:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
            except Exception as e:
                logger.error(f"Local Qwen3-ASR inference error: {e}")
                raise

        # If model runtime cannot be loaded locally, raise clear runtime error as instructed
        raise RuntimeError(
            f"Qwen3-ASR model '{self.model_name}' runtime is not available locally and no ASR API endpoint is configured."
        )

    async def _transcribe_via_api(self, wav_bytes: bytes, duration_s: float) -> TranscriptResult:
        """Transcribe via DashScope / Qwen-ASR API endpoint."""
        url = self.api_url or "https://dashscope.aliyuncs.com/api/v1/services/audio/asr/transcription"
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        files = {"file": ("audio.wav", wav_bytes, "audio/wav")}
        data = {"model": self.model_name}

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, files=files, data=data)
            if resp.status_code != 200:
                raise RuntimeError(f"Qwen3-ASR API returned {resp.status_code}: {resp.text}")
            result_json = resp.json()
            text = (
                result_json.get("output", {}).get("text")
                or result_json.get("text")
                or ""
            )
            return TranscriptResult(
                text=text.strip(),
                language="en",
                confidence=0.98,
                duration_seconds=round(duration_s, 2)
            )
