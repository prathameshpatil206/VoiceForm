from abc import ABC, abstractmethod
from datetime import datetime, timezone
import logging
import uuid
from typing import Dict, List, Optional
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import ProfileFieldModel, UserProfileModel
from app.db.session import get_session_factory
from app.schemas.profile import (
    ProfileFieldSchema,
    ProfileSource,
    UserProfileSchema
)

logger = logging.getLogger("voiceform.db.repository")


class ProfileRepository(ABC):
    @abstractmethod
    async def get_or_create_profile(self, profile_id: str) -> UserProfileSchema:
        pass

    @abstractmethod
    async def get_profile(self, profile_id: str) -> Optional[UserProfileSchema]:
        pass

    @abstractmethod
    async def upsert_field(
        self,
        profile_id: str,
        canonical_key: str,
        value: str,
        source: ProfileSource = ProfileSource.USER_SPOKEN,
        confidence: float = 1.0
    ) -> ProfileFieldSchema:
        pass

    @abstractmethod
    async def delete_field(self, profile_id: str, canonical_key: str) -> bool:
        pass

    @abstractmethod
    async def delete_profile(self, profile_id: str) -> bool:
        pass

    @abstractmethod
    async def clear_profile_fields(self, profile_id: str) -> bool:
        pass

    @abstractmethod
    async def set_profile_enabled(self, profile_id: str, is_enabled: bool) -> bool:
        pass


class SQLAlchemyProfileRepository(ProfileRepository):
    def __init__(self, session_factory: Optional[async_sessionmaker[AsyncSession]] = None):
        self.session_factory = session_factory or get_session_factory()

    def _to_field_schema(self, m: ProfileFieldModel) -> ProfileFieldSchema:
        # Fallback created_at / updated_at if None
        now = datetime.now(timezone.utc)
        return ProfileFieldSchema(
            id=m.id,
            profile_id=m.profile_id,
            canonical_key=m.canonical_key,
            value=m.value,
            source=ProfileSource(m.source) if m.source in ProfileSource._value2member_map_ else ProfileSource.USER_SPOKEN,
            confidence=m.confidence,
            created_at=m.created_at or now,
            updated_at=m.updated_at or now
        )

    def _to_profile_schema(self, p: UserProfileModel) -> UserProfileSchema:
        now = datetime.now(timezone.utc)
        fields_dict: Dict[str, ProfileFieldSchema] = {}
        for f in (p.fields or []):
            fields_dict[f.canonical_key] = self._to_field_schema(f)

        return UserProfileSchema(
            id=p.id,
            is_enabled=p.is_enabled,
            fields=fields_dict,
            created_at=p.created_at or now,
            updated_at=p.updated_at or now
        )

    async def get_or_create_profile(self, profile_id: str) -> UserProfileSchema:
        async with self.session_factory() as session:
            stmt = select(UserProfileModel).where(UserProfileModel.id == profile_id)
            res = await session.execute(stmt)
            profile = res.scalar_one_or_none()

            if not profile:
                profile = UserProfileModel(
                    id=profile_id,
                    is_enabled=True,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc)
                )
                session.add(profile)
                try:
                    await session.commit()
                except Exception:
                    await session.rollback()
                # Re-query with eager load
                res = await session.execute(stmt)
                profile = res.scalar_one()

            return self._to_profile_schema(profile)

    async def get_profile(self, profile_id: str) -> Optional[UserProfileSchema]:
        async with self.session_factory() as session:
            stmt = select(UserProfileModel).where(UserProfileModel.id == profile_id)
            res = await session.execute(stmt)
            profile = res.scalar_one_or_none()
            if not profile:
                return None
            return self._to_profile_schema(profile)

    async def upsert_field(
        self,
        profile_id: str,
        canonical_key: str,
        value: str,
        source: ProfileSource = ProfileSource.USER_SPOKEN,
        confidence: float = 1.0
    ) -> ProfileFieldSchema:
        # Ensure user profile exists first
        await self.get_or_create_profile(profile_id)

        now = datetime.now(timezone.utc)
        async with self.session_factory() as session:
            stmt = select(ProfileFieldModel).where(
                ProfileFieldModel.profile_id == profile_id,
                ProfileFieldModel.canonical_key == canonical_key
            )
            res = await session.execute(stmt)
            field = res.scalar_one_or_none()

            if field:
                field.value = value
                field.source = source.value
                field.confidence = confidence
                field.updated_at = now
            else:
                field = ProfileFieldModel(
                    id=str(uuid.uuid4()),
                    profile_id=profile_id,
                    canonical_key=canonical_key,
                    value=value,
                    source=source.value,
                    confidence=confidence,
                    created_at=now,
                    updated_at=now
                )
                session.add(field)

            # Update parent profile updated_at
            p_stmt = update(UserProfileModel).where(UserProfileModel.id == profile_id).values(updated_at=now)
            await session.execute(p_stmt)

            await session.commit()
            await session.refresh(field)
            return self._to_field_schema(field)

    async def delete_field(self, profile_id: str, canonical_key: str) -> bool:
        async with self.session_factory() as session:
            stmt = delete(ProfileFieldModel).where(
                ProfileFieldModel.profile_id == profile_id,
                ProfileFieldModel.canonical_key == canonical_key
            )
            res = await session.execute(stmt)
            await session.commit()
            rowcount = getattr(res, "rowcount", 0) or 0
            return bool(rowcount > 0)

    async def delete_profile(self, profile_id: str) -> bool:
        async with self.session_factory() as session:
            stmt = delete(UserProfileModel).where(UserProfileModel.id == profile_id)
            res = await session.execute(stmt)
            await session.commit()
            rowcount = getattr(res, "rowcount", 0) or 0
            return bool(rowcount > 0)

    async def clear_profile_fields(self, profile_id: str) -> bool:
        async with self.session_factory() as session:
            stmt = delete(ProfileFieldModel).where(ProfileFieldModel.profile_id == profile_id)
            res = await session.execute(stmt)
            await session.commit()
            return True

    async def set_profile_enabled(self, profile_id: str, is_enabled: bool) -> bool:
        await self.get_or_create_profile(profile_id)
        now = datetime.now(timezone.utc)
        async with self.session_factory() as session:
            stmt = (
                update(UserProfileModel)
                .where(UserProfileModel.id == profile_id)
                .values(is_enabled=is_enabled, updated_at=now)
            )
            res = await session.execute(stmt)
            await session.commit()
            rowcount = getattr(res, "rowcount", 0) or 0
            return bool(rowcount > 0)
