"""Async SQLAlchemy engine + session plumbing."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    pass


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _build_engine() -> AsyncEngine:
    settings = get_settings()
    kwargs: dict = {"pool_pre_ping": True, "future": True}
    # SQLite (used by the test suite) does not support connection pooling args.
    if not settings.database_url.startswith("sqlite"):
        kwargs |= {
            "pool_size": settings.db_pool_size,
            "max_overflow": settings.db_max_overflow,
        }
    return create_async_engine(settings.database_url, **kwargs)


@asynccontextmanager
async def lifespan_engine() -> AsyncIterator[AsyncEngine]:
    global _engine, _sessionmaker
    _engine = _build_engine()
    _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    try:
        yield _engine
    finally:
        await _engine.dispose()
        _engine, _sessionmaker = None, None


async def get_session() -> AsyncIterator[AsyncSession]:
    if _sessionmaker is None:
        raise RuntimeError("engine not initialised; app lifespan did not run")
    async with _sessionmaker() as session:
        yield session
