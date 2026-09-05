import os
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

class AppConfig(BaseModel):
    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", "8765"))
    PROTOCOL_VERSION: int = 1
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    ALLOWED_ORIGINS: list[str] = ["*"]

    # Milestone 4: AI Configuration
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "qwen2.5:1.5b")
    LLM_TIMEOUT: float = float(os.getenv("LLM_TIMEOUT", "60.0"))
    ASR_MODEL: str = os.getenv("ASR_MODEL", "Qwen/Qwen3-ASR-0.6B")
    VAD_THRESHOLD: float = float(os.getenv("VAD_THRESHOLD", "0.5"))
    VAD_SILENCE_DURATION_MS: int = int(os.getenv("VAD_SILENCE_DURATION_MS", "800"))
    AUDIO_SAMPLE_RATE: int = 16000

    # Milestone 5: Rime TTS Configuration
    RIME_API_KEY: str = os.getenv("RIME_API_KEY", "")
    RIME_BASE_URL: str = os.getenv("RIME_BASE_URL", "https://users.rime.ai/v1/rime-tts")
    RIME_SPEAKER: str = os.getenv("RIME_SPEAKER", "amber")
    RIME_MODEL_ID: str = os.getenv("RIME_MODEL_ID", "mist")
    RIME_AUDIO_FORMAT: str = os.getenv("RIME_AUDIO_FORMAT", "pcm")
    RIME_SAMPLING_RATE: int = int(os.getenv("RIME_SAMPLING_RATE", "16000"))
    TTS_TIMEOUT: float = float(os.getenv("TTS_TIMEOUT", "15.0"))
    TTS_SAFETY_MAX_CHARS: int = int(os.getenv("TTS_SAFETY_MAX_CHARS", "600"))

    # Milestone 7: User Profile & Persistence Configuration
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/voiceform")
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    REDIS_TTL_SECONDS: int = int(os.getenv("REDIS_TTL_SECONDS", "3600"))
    PROFILE_CONFIDENCE_THRESHOLD: float = float(os.getenv("PROFILE_CONFIDENCE_THRESHOLD", "0.75"))
    ENABLE_PROFILE_PERSISTENCE: bool = os.getenv("ENABLE_PROFILE_PERSISTENCE", "true").lower() in ("true", "1", "yes")
    DEFAULT_PROFILE_ID: str = os.getenv("DEFAULT_PROFILE_ID", "default_user")

config = AppConfig()
settings = config
