import logging
from typing import Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from app.db.models import Base
from app.db.session import get_engine

logger = logging.getLogger("voiceform.db.migration")


async def run_migrations(database_url: Optional[str] = None) -> bool:
    """
    Executes initial M7 schema migration creating user_profiles, profile_fields tables
    and unique indices asynchronously.
    """
    try:
        engine: AsyncEngine = get_engine(database_url)
        async with engine.begin() as conn:
            # Create schema_migrations table
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version VARCHAR(64) PRIMARY KEY,
                    applied_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            """))

            # Create Base tables (UserProfileModel and ProfileFieldModel)
            await conn.run_sync(Base.metadata.create_all)

            # Record migration version
            await conn.execute(text("""
                INSERT INTO schema_migrations (version)
                VALUES ('m7_initial_user_profile')
                ON CONFLICT (version) DO NOTHING
            """))

        logger.info("✅ Database migrations applied successfully (version: m7_initial_user_profile)")
        return True
    except Exception as e:
        logger.error(f"❌ Database migration failed: {e}")
        return False
