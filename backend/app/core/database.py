from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import AsyncGenerator

from app.core.config import settings


# ─── Async Engine (FastAPI) ────────────────────────────────────────────────────
async_engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ─── Sync Engine (Celery Workers) ─────────────────────────────────────────────
sync_engine = create_engine(
    settings.database_sync_url,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
)

SyncSessionLocal = sessionmaker(bind=sync_engine, expire_on_commit=False)


# ─── FastAPI dependency ────────────────────────────────────────────────────────
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def get_sync_db() -> Session:
    """Celery 워커에서 사용하는 동기 DB 세션."""
    return SyncSessionLocal()


async def create_tables():
    """애플리케이션 시작 시 테이블 생성 (개발용)."""
    from app.models.base import Base
    # import all models so metadata is populated
    import app.models.project    # noqa: F401
    import app.models.dwg_object  # noqa: F401

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
