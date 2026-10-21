"""Database connection pool, async SQLAlchemy 2.x engine, and session management."""

import asyncpg
from typing import AsyncGenerator, Optional
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from app.core.config import settings

# Native asyncpg connection pool
_pool: Optional[asyncpg.Pool] = None


def get_asyncpg_url() -> str:
    """Strips SQLAlchemy driver prefixes for native asyncpg compatibility."""
    return settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")


async def get_db_pool() -> asyncpg.Pool:
    """Returns or initializes the singleton asyncpg connection pool."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            get_asyncpg_url(),
            min_size=1,
            max_size=10,
            timeout=10,
        )
    return _pool


async def close_db_pool() -> None:
    """Closes the asyncpg connection pool on application shutdown."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


from sqlalchemy.pool import NullPool

# SQLAlchemy 2.x Async Engine and Session Factory
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    poolclass=NullPool if settings.ENVIRONMENT in ("testing", "test") else None,
    echo=settings.DEBUG and settings.ENVIRONMENT == "development",
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def ping_database() -> bool:
    """Performs an active probe to verify PostgreSQL connectivity."""
    try:
        conn = await asyncpg.connect(get_asyncpg_url(), timeout=3)
        val = await conn.fetchval("SELECT 1;")
        await conn.close()
        return val == 1
    except Exception:
        return False
