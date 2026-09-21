"""Engine and session factory. No SQL lives here — see repositories/."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.config import Settings


def build_engine(settings: Settings) -> AsyncEngine:
    kwargs: dict[str, object] = {"pool_pre_ping": True, "future": True}
    if not settings.database_url.startswith("sqlite"):
        kwargs["pool_size"] = settings.db_pool_size
        kwargs["max_overflow"] = settings.db_max_overflow
    return create_async_engine(settings.database_url, **kwargs)


def build_sessionmaker(engine: AsyncEngine) -> async_sessionmaker:
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
