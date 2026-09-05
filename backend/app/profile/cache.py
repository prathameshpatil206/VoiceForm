import json
import logging
import time
from typing import Any, Dict, Optional
import redis.asyncio as aioredis
from app.config import config
from app.schemas.profile import UserProfileSchema

logger = logging.getLogger("voiceform.profile.cache")


class ProfileCache:
    """
    Redis Caching Layer for VoiceForm User Profiles.
    Provides fast sub-millisecond retrieval with automatic fallback if Redis is unavailable.
    """

    def __init__(self, redis_url: Optional[str] = None, ttl: Optional[int] = None):
        self.redis_url = redis_url or config.REDIS_URL
        self.ttl = ttl or config.REDIS_TTL_SECONDS
        self._client: Optional[aioredis.Redis] = None
        self.hits = 0
        self.misses = 0
        self.last_latency_ms: float = 0.0

    async def _get_client(self) -> Optional[aioredis.Redis]:
        if self._client is None:
            try:
                self._client = aioredis.from_url(
                    self.redis_url,
                    decode_responses=True,
                    protocol=2,  # Force RESP2 for universal compatibility
                    socket_connect_timeout=1.0,
                    socket_timeout=1.0
                )
            except Exception as e:
                logger.warning(f"Could not connect to Redis at {self.redis_url}: {e}")
                self._client = None
        return self._client

    def _make_key(self, profile_id: str) -> str:
        return f"voiceform:profile:{profile_id}"

    async def is_available(self) -> bool:
        try:
            client = await self._get_client()
            if not client:
                return False
            res = await client.ping()
            return res
        except Exception:
            return False

    async def get_profile(self, profile_id: str) -> Optional[UserProfileSchema]:
        t0 = time.perf_counter()
        try:
            client = await self._get_client()
            if not client:
                self.misses += 1
                return None

            key = self._make_key(profile_id)
            data_str = await client.get(key)
            self.last_latency_ms = (time.perf_counter() - t0) * 1000

            if not data_str:
                self.misses += 1
                return None

            self.hits += 1
            data_dict = json.loads(data_str)
            return UserProfileSchema.model_validate(data_dict)
        except Exception as e:
            self.last_latency_ms = (time.perf_counter() - t0) * 1000
            self.misses += 1
            logger.warning(f"Redis get_profile failed for {profile_id} (falling back to DB): {e}")
            return None

    async def set_profile(self, profile: UserProfileSchema, ttl: Optional[int] = None) -> bool:
        try:
            client = await self._get_client()
            if not client:
                return False

            key = self._make_key(profile.id)
            effective_ttl = ttl or self.ttl
            payload_str = profile.model_dump_json()
            await client.set(key, payload_str, ex=effective_ttl)
            return True
        except Exception as e:
            logger.warning(f"Redis set_profile failed for {profile.id}: {e}")
            return False

    async def invalidate_profile(self, profile_id: str) -> bool:
        try:
            client = await self._get_client()
            if not client:
                return False

            key = self._make_key(profile_id)
            await client.delete(key)
            return True
        except Exception as e:
            logger.warning(f"Redis invalidate_profile failed for {profile_id}: {e}")
            return False

    async def close(self) -> None:
        if self._client:
            try:
                await self._client.close()
            except Exception:
                pass
            self._client = None
