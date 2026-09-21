"""Wiring: build the long-lived objects an app instance needs.

Kept out of main.py so the test suite can assemble the same application with a
SQLite engine, a fake Redis and an injected provider, without monkeypatching.
"""

from __future__ import annotations

from fastapi import FastAPI
from redis.asyncio import Redis

from app.config import Settings
from app.db import build_engine, build_sessionmaker
from app.providers.cache import CacheProvider
from app.providers.triage.factory import build_triage_provider
from app.services.triage import TriageService


def attach_state(
    app: FastAPI,
    settings: Settings,
    *,
    engine=None,
    redis: Redis | None = None,
    triage_provider=None,
) -> None:
    app.state.settings = settings
    app.state.draining = False
    app.state.engine = engine if engine is not None else build_engine(settings)
    app.state.sessionmaker = build_sessionmaker(app.state.engine)
    app.state.redis = redis if redis is not None else Redis.from_url(
        settings.redis_url, decode_responses=True
    )
    app.state.cache = CacheProvider(app.state.redis, namespace=settings.app_name)
    app.state.triage_provider = triage_provider or build_triage_provider(settings)
    app.state.triage_service = TriageService(
        provider=app.state.triage_provider, cache=app.state.cache, settings=settings
    )


async def close_state(app: FastAPI) -> None:
    provider = getattr(app.state, "triage_provider", None)
    if provider is not None and hasattr(provider, "aclose"):
        await provider.aclose()
    redis = getattr(app.state, "redis", None)
    if redis is not None:
        await redis.aclose()
    engine = getattr(app.state, "engine", None)
    if engine is not None:
        await engine.dispose()
