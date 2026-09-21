"""Test harness.

Two deliberate substitutions and nothing else: SQLite for PostgreSQL and
fakeredis for Redis, so the suite is hermetic and runs in under a second on a
CI runner with no services. Everything else — routes, services, repositories,
the triage policy — is the production code path.

The provider is injected per test. That is how a probabilistic component gets a
deterministic test suite: CI never calls a model, it calls a fake that fails,
times out or returns prose exactly when the test asks it to.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable

import fakeredis.aioredis
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.db import build_engine
from app.main import create_app
from app.models import Base
from app.providers.triage.simulated import SimulatedTriage


class FlakyProvider:
    """Fails for the first `failures` calls, then succeeds."""

    name = "llm:flaky"

    def __init__(self, error: Exception, failures: int = 1) -> None:
        self._error = error
        self._remaining = failures
        self.calls = 0

    async def triage(self, text: str, location: str):
        self.calls += 1
        if self._remaining > 0:
            self._remaining -= 1
            raise self._error
        return await SimulatedTriage(latency_ms=0).triage(text, location)


class AlwaysRaisingProvider:
    name = "llm:broken"

    def __init__(self, error: Exception) -> None:
        self._error = error
        self.calls = 0

    async def triage(self, text: str, location: str):
        self.calls += 1
        raise self._error


@pytest.fixture
def make_settings(tmp_path) -> Callable[..., Settings]:
    def _make(**overrides) -> Settings:
        base = {
            "database_url": f"sqlite+aiosqlite:///{tmp_path}/civicpulse-test.db",
            "redis_url": "redis://localhost:6379/0",
            "triage_provider": "simulated",
            "simulated_latency_ms": 0,
            "log_level": "WARNING",
            "environment": "test",
        }
        base.update(overrides)
        return Settings(_env_file=None, **base)

    return _make


@pytest_asyncio.fixture
async def app_factory(make_settings) -> AsyncIterator[Callable]:
    resources: list[tuple] = []

    async def _build(provider=None, **setting_overrides):
        settings = make_settings(**setting_overrides)
        engine = build_engine(settings)
        # Production schema comes from Alembic; the test harness creates the
        # same metadata directly so the suite needs no migration runner.
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        app = create_app(
            settings,
            engine=engine,
            redis=redis,
            triage_provider=provider or SimulatedTriage(latency_ms=0),
        )
        resources.append((engine, redis))
        return app

    yield _build

    for engine, redis in resources:
        await redis.aclose()
        await engine.dispose()


@pytest_asyncio.fixture
async def client_factory(app_factory) -> AsyncIterator[Callable]:
    clients: list[AsyncClient] = []

    async def _build(provider=None, **setting_overrides) -> AsyncClient:
        app = await app_factory(provider=provider, **setting_overrides)
        client = AsyncClient(
            transport=ASGITransport(app=app), base_url="http://civicpulse.test"
        )
        client.app = app  # type: ignore[attr-defined]
        clients.append(client)
        return client

    yield _build

    for client in clients:
        await client.aclose()


@pytest_asyncio.fixture
async def client(client_factory) -> AsyncClient:
    return await client_factory()


VALID_COMPLAINT = {
    "text": "Burst water main flooding Street 12 since fajr, water entering ground floors.",
    "location": "Street 12, G-9/1, Islamabad",
    "reporter_contact": "0300-1234567",
}
