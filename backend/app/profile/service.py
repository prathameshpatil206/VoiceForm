from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
from app.config import config
from app.db.repository import ProfileRepository, SQLAlchemyProfileRepository
from app.profile.cache import ProfileCache
from app.profile.normalizer import normalize_form_field, normalize_key_string
from app.profile.safety import is_prohibited_candidate, is_sensitive_field
from app.schemas.form import FormField, PageScanResult
from app.schemas.profile import (
    FieldMatchStatus,
    ProfileCandidate,
    ProfileFieldSchema,
    ProfileMatchCandidate,
    ProfileSource,
    UserProfileSchema
)

logger = logging.getLogger("voiceform.profile.service")

REUSABLE_PROFILE_KEYS = {
    "first_name",
    "last_name",
    "full_name",
    "email",
    "phone",
    "address",
    "city",
    "state",
    "postal_code",
    "country",
    "date_of_birth",
    "gender",
    "company",
    "job_title"
}


class ProfileService:
    """
    Core business service for User Profile management, normalization,
    caching, retrieval against active forms, and safe persistence.
    """

    def __init__(
        self,
        repository: Optional[ProfileRepository] = None,
        cache: Optional[ProfileCache] = None,
        confidence_threshold: Optional[float] = None
    ):
        self.repository = repository or SQLAlchemyProfileRepository()
        self.cache = cache or ProfileCache()
        self.confidence_threshold = (
            confidence_threshold if confidence_threshold is not None else config.PROFILE_CONFIDENCE_THRESHOLD
        )
        self._fallback_memory_profiles: Dict[str, UserProfileSchema] = {}

    async def get_profile(self, profile_id: Optional[str] = None) -> UserProfileSchema:
        pid = profile_id or config.DEFAULT_PROFILE_ID

        # 1. Try Redis Cache
        try:
            cached = await self.cache.get_profile(pid)
            if cached:
                return cached
        except Exception as ce:
            logger.debug(f"Cache check skipped: {ce}")

        # 2. Database Lookup
        try:
            profile = await self.repository.get_or_create_profile(pid)
            # 3. Populate Redis Cache
            try:
                await self.cache.set_profile(profile)
            except Exception:
                pass
            return profile
        except Exception as de:
            logger.warning(f"Database lookup failed for profile {pid} (using in-memory fallback): {de}")
            if pid not in self._fallback_memory_profiles:
                now = datetime.now(timezone.utc)
                self._fallback_memory_profiles[pid] = UserProfileSchema(
                    id=pid,
                    is_enabled=True,
                    fields={},
                    created_at=now,
                    updated_at=now
                )
            return self._fallback_memory_profiles[pid]

    async def upsert_field(
        self,
        canonical_key: str,
        value: str,
        profile_id: Optional[str] = None,
        source: ProfileSource = ProfileSource.USER_SPOKEN,
        confidence: float = 1.0
    ) -> ProfileFieldSchema:
        pid = profile_id or config.DEFAULT_PROFILE_ID

        # Check safety guard
        is_prohibited, reason = is_prohibited_candidate(canonical_key, value)
        if is_prohibited:
            logger.warning(f"Rejected sensitive field persistence: key='{canonical_key}', reason={reason}")
            raise ValueError(f"Prohibited sensitive field: {reason}")

        # Normalize canonical key
        norm_key = normalize_key_string(canonical_key) or canonical_key.lower().strip()

        # Check profile persistence enabled status
        profile = await self.get_profile(pid)
        now = datetime.now(timezone.utc)
        if not profile.is_enabled:
            logger.info(f"Profile persistence is disabled for {pid}; skipping write.")
            return ProfileFieldSchema(
                id="transient",
                profile_id=pid,
                canonical_key=norm_key,
                value=value,
                source=source,
                confidence=confidence,
                created_at=now,
                updated_at=now
            )

        # Persist to database
        try:
            saved = await self.repository.upsert_field(
                profile_id=pid,
                canonical_key=norm_key,
                value=value,
                source=source,
                confidence=confidence
            )
            try:
                await self.cache.invalidate_profile(pid)
            except Exception:
                pass
            return saved
        except Exception as de:
            logger.warning(f"Database write failed for {pid}.{norm_key} (persisting in fallback store): {de}")
            field = ProfileFieldSchema(
                id=f"fb_{norm_key}",
                profile_id=pid,
                canonical_key=norm_key,
                value=value,
                source=source,
                confidence=confidence,
                created_at=now,
                updated_at=now
            )
            prof = await self.get_profile(pid)
            prof.fields[norm_key] = field
            prof.updated_at = now
            return field

    async def delete_field(self, canonical_key: str, profile_id: Optional[str] = None) -> bool:
        pid = profile_id or config.DEFAULT_PROFILE_ID
        norm_key = normalize_key_string(canonical_key) or canonical_key.lower().strip()
        try:
            deleted = await self.repository.delete_field(pid, norm_key)
            try:
                await self.cache.invalidate_profile(pid)
            except Exception:
                pass
            return deleted
        except Exception:
            if pid in self._fallback_memory_profiles:
                return bool(self._fallback_memory_profiles[pid].fields.pop(norm_key, None))
            return False

    async def clear_profile(self, profile_id: Optional[str] = None) -> bool:
        pid = profile_id or config.DEFAULT_PROFILE_ID
        try:
            cleared = await self.repository.clear_profile_fields(pid)
            try:
                await self.cache.invalidate_profile(pid)
            except Exception:
                pass
            return cleared
        except Exception:
            if pid in self._fallback_memory_profiles:
                self._fallback_memory_profiles[pid].fields.clear()
                return True
            return False

    async def delete_profile(self, profile_id: Optional[str] = None) -> bool:
        pid = profile_id or config.DEFAULT_PROFILE_ID
        try:
            deleted = await self.repository.delete_profile(pid)
            try:
                await self.cache.invalidate_profile(pid)
            except Exception:
                pass
            return deleted
        except Exception:
            return bool(self._fallback_memory_profiles.pop(pid, None))

    async def set_enabled(self, is_enabled: bool, profile_id: Optional[str] = None) -> bool:
        pid = profile_id or config.DEFAULT_PROFILE_ID
        try:
            updated = await self.repository.set_profile_enabled(pid, is_enabled)
            try:
                await self.cache.invalidate_profile(pid)
            except Exception:
                pass
            return updated
        except Exception:
            prof = await self.get_profile(pid)
            prof.is_enabled = is_enabled
            return True

    async def get_candidate_values_for_schema(
        self,
        schema: PageScanResult,
        profile_id: Optional[str] = None
    ) -> List[ProfileMatchCandidate]:
        """
        Matches fields from a scanned page against the persistent profile.
        Returns candidate matches distinguished as KNOWN, UNKNOWN, or AMBIGUOUS.
        """
        try:
            pid = profile_id or config.DEFAULT_PROFILE_ID
            profile = await self.get_profile(pid)

            candidates: List[ProfileMatchCandidate] = []
            if not profile.is_enabled:
                return candidates

            # Flatten all fields from forms + orphans
            all_fields: List[FormField] = []
            for form in schema.forms:
                all_fields.extend(form.fields)
            all_fields.extend(schema.orphanFields)

            for f in all_fields:
                # Hard safety filter: Skip sensitive fields (passwords, OTPs, etc.)
                if is_sensitive_field(f):
                    continue

                canon_key = normalize_form_field(f)
                if not canon_key:
                    candidates.append(
                        ProfileMatchCandidate(
                            field_id=f.id,
                            canonical_key=None,
                            status=FieldMatchStatus.UNKNOWN
                        )
                    )
                    continue

                if canon_key in profile.fields:
                    stored = profile.fields[canon_key]
                    candidates.append(
                        ProfileMatchCandidate(
                            field_id=f.id,
                            canonical_key=canon_key,
                            status=FieldMatchStatus.KNOWN,
                            value=stored.value,
                            confidence=stored.confidence,
                            source=stored.source
                        )
                    )
                else:
                    candidates.append(
                        ProfileMatchCandidate(
                            field_id=f.id,
                            canonical_key=canon_key,
                            status=FieldMatchStatus.UNKNOWN
                        )
                    )

            return candidates
        except Exception as e:
            logger.warning(f"Could not calculate candidate values for schema: {e}")
            return []

    def extract_profile_candidates_from_actions(
        self,
        actions: List[Dict[str, Any]],
        schema: PageScanResult,
        source: ProfileSource = ProfileSource.USER_SPOKEN
    ) -> List[ProfileCandidate]:
        """
        Extracts reusable profile candidates from executed form fill actions.
        Evaluates profile-worthiness and enforces security safety filters.
        """
        candidates: List[ProfileCandidate] = []
        field_map: Dict[str, FormField] = {}
        for form in schema.forms:
            for f in form.fields:
                field_map[f.id] = f
        for f in schema.orphanFields:
            field_map[f.id] = f

        for act in actions:
            fid = act.get("field_id")
            val = act.get("value")
            if not fid or val is None or fid not in field_map:
                continue

            field = field_map[fid]

            # 1. Skip sensitive/secret fields
            if is_sensitive_field(field):
                continue

            # 2. Normalize canonical key
            canon_key = normalize_form_field(field)
            if not canon_key:
                continue

            # 3. Check profile-worthiness (must be reusable profile field)
            if canon_key not in REUSABLE_PROFILE_KEYS:
                continue

            str_val = str(val).strip()
            # 4. Check safety guard on candidate value
            is_proh, _ = is_prohibited_candidate(canon_key, str_val)
            if is_proh:
                continue

            candidates.append(
                ProfileCandidate(
                    canonical_key=canon_key,
                    value=str_val,
                    confidence=0.95,
                    source=source
                )
            )

        return candidates

    async def save_eligible_candidates(
        self,
        candidates: List[ProfileCandidate],
        profile_id: Optional[str] = None
    ) -> List[ProfileFieldSchema]:
        """
        Persists profile candidates that exceed the confidence threshold.
        """
        pid = profile_id or config.DEFAULT_PROFILE_ID
        saved_fields: List[ProfileFieldSchema] = []

        for cand in candidates:
            if cand.confidence >= self.confidence_threshold:
                try:
                    saved = await self.upsert_field(
                        canonical_key=cand.canonical_key,
                        value=cand.value,
                        profile_id=pid,
                        source=cand.source,
                        confidence=cand.confidence
                    )
                    saved_fields.append(saved)
                except ValueError as e:
                    logger.warning(f"Candidate rejected during save: {e}")

        return saved_fields
