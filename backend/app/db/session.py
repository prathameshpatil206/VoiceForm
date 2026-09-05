import asyncio
import logging
from typing import AsyncGenerator, Optional
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine
)
from sqlalchemy import text
from app.config import config

logger = logging.getLogger("voiceform.db")

_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def get_engine(database_url: Optional[str] = None) -> AsyncEngine:
    global _engine, _session_factory
    url = database_url or config.DATABASE_URL

    if _engine is None or str(_engine.url) != url:
        # Configure connect_args based on database type
        connect_args = {}
        if "sqlite" in url:
            connect_args = {"check_same_thread": False}
        else:
            connect_args = {"timeout": 2.0}

        _engine = create_async_engine(
            url,
            echo=False,
            future=True,
            connect_args=connect_args
        )
        _session_factory = async_sessionmaker(
            bind=_engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
        logger.info(f"Initialized Database Engine for: {url.split('@')[-1] if '@' in url else url}")

    return _engine


def get_session_factory(database_url: Optional[str] = None) -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        get_engine(database_url)
    return _session_factory  # type: ignore


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def check_db_health(database_url: Optional[str] = None) -> bool:
    try:
        engine = get_engine(database_url)
        async with asyncio.timeout(2.0):
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.warning(f"Database health check failed: {e}")
        return False


async def close_db_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("Database engine closed")
