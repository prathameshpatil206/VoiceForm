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

DEFAULT_PROMPT_BIAS = (
    "My name is Prathamesh, Sai Siddu, Alex Morgan. "
    "Fill first name, last name, email address, phone number, street address, city, state, postal code."
)

class Qwen3ASRProvider(ASRProvider):
    """
    Qwen3-ASR speech-to-text inference provider.
    Supports ultra-fast cloud Whisper (Groq) as well as high-accuracy local Whisper / faster-whisper.
    """

    def __init__(
        self,
        model_name: str = config.ASR_MODEL,
        api_url: Optional[str] = os.getenv("QWEN_ASR_API_URL"),
        api_key: Optional[str] = os.getenv("DASHSCOPE_API_KEY"),
        groq_api_key: Optional[str] = os.getenv("GROQ_API_KEY")
    ) -> None:
        self.model_name = model_name
        self.api_url = api_url
        self.api_key = api_key
        self.groq_api_key = groq_api_key if groq_api_key and groq_api_key != "your_groq_api_key_here" else None
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

        whisper_model_name = os.getenv("WHISPER_MODEL", "base")

        try:
            # 1. Local Whisper engine with high-accuracy 'base' model
            try:
                import whisper
                logger.info(f"Loading local Whisper ({whisper_model_name}) engine...")
                try:
                    self._local_model = whisper.load_model(whisper_model_name)
                    self._initialized = True
                    logger.info(f"✅ Local ASR engine loaded successfully (whisper {whisper_model_name})")
                    return
                except Exception as e_load:
                    logger.warning(f"Could not load whisper '{whisper_model_name}', falling back to 'tiny': {e_load}")
                    self._local_model = whisper.load_model("tiny")
                    self._initialized = True
                    logger.info("✅ Local ASR engine loaded successfully (whisper tiny fallback)")
                    return
            except Exception as e_w:
                logger.debug(f"whisper package not available: {e_w}")

            # 2. Faster-whisper engine
            try:
                from faster_whisper import WhisperModel
                self._local_model = WhisperModel(whisper_model_name, device="cpu", compute_type="int8")
                self._initialized = True
                logger.info(f"✅ Local ASR engine loaded successfully (faster-whisper {whisper_model_name})")
                return
            except Exception as e_fw:
                logger.debug(f"faster-whisper not available: {e_fw}")

            # 3. Qwen3-ASR model
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

        except Exception as e:
            logger.warning(f"Local ASR model could not be loaded into memory: {e}")
            self._initialized = True

    async def transcribe(
        self, audio_data: bytes, sample_rate: int = 16000
    ) -> TranscriptResult:
        """
        Transcribes 16kHz speech audio with high accuracy and low latency.
        """
        wav_bytes = self._pcm_to_wav(audio_data, sample_rate)
        duration_s = len(audio_data) / (sample_rate * 2.0)

        # 1. If Groq API key is present, use ultra-fast sub-200ms cloud Whisper
        groq_key = self.groq_api_key or os.getenv("GROQ_API_KEY")
        if groq_key and groq_key != "your_groq_api_key_here":
            try:
                return await self._transcribe_via_groq(wav_bytes, duration_s, groq_key)
            except Exception as e_groq:
                logger.warning(f"Groq Whisper transcription failed; falling back to local: {e_groq}")

        # 2. If DashScope API URL is configured, query the API endpoint
        if self.api_url or self.api_key:
            try:
                return await self._transcribe_via_api(wav_bytes, duration_s)
            except Exception as e_api:
                logger.warning(f"ASR API call failed; falling back to local: {e_api}")

        # 3. Local inference via loaded Whisper model
        self._init_local_model()

        if self._local_model is not None:
            try:
                import numpy as np
                audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                    tmp.write(wav_bytes)
                    tmp_path = tmp.name

                try:
                    if hasattr(self._local_model, "transcribe"):
                        # 1. openai-whisper model
                        try:
                            res = self._local_model.transcribe(
                                audio_np,
                                fp16=False,
                                initial_prompt=DEFAULT_PROMPT_BIAS,
                                language="en"
                            )
                            if isinstance(res, dict):
                                text = res.get("text", "").strip()
                                return TranscriptResult(
                                    text=text,
                                    language=res.get("language", "en"),
                                    confidence=0.96,
                                    duration_seconds=round(duration_s, 2)
                                )
                        except Exception as e_np:
                            logger.debug(f"Direct numpy transcribe failed: {e_np}")

                        # 2. faster_whisper model
                        try:
                            segments, info = self._local_model.transcribe(
                                tmp_path,
                                beam_size=1,
                                initial_prompt=DEFAULT_PROMPT_BIAS,
                                language="en"
                            )
                            text = " ".join([s.text for s in segments]).strip()
                            lang = getattr(info, "language", "en")
                            return TranscriptResult(
                                text=text,
                                language=lang,
                                confidence=0.96,
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
                        try:
                            os.remove(tmp_path)
                        except Exception:
                            pass
            except Exception as e:
                logger.error(f"Local ASR inference error: {e}")
                raise

        raise RuntimeError(
            f"ASR model runtime is not available locally and no ASR API endpoint is configured."
        )

    async def _transcribe_via_groq(self, wav_bytes: bytes, duration_s: float, api_key: str) -> TranscriptResult:
        """High-speed Groq Whisper cloud endpoint (sub-200ms latency, high accuracy)."""
        url = "https://api.groq.com/openai/v1/audio/transcriptions"
        headers = {"Authorization": f"Bearer {api_key}"}
        files = {"file": ("audio.wav", wav_bytes, "audio/wav")}
        data = {
            "model": "whisper-large-v3-turbo",
            "prompt": DEFAULT_PROMPT_BIAS,
            "response_format": "json",
            "language": "en"
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, headers=headers, files=files, data=data)
            if resp.status_code != 200:
                raise RuntimeError(f"Groq Whisper returned {resp.status_code}: {resp.text}")
            result_json = resp.json()
            text = result_json.get("text", "").strip()
            return TranscriptResult(
                text=text,
                language="en",
                confidence=0.99,
                duration_seconds=round(duration_s, 2)
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
