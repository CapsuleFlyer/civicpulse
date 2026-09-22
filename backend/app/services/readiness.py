"""Readiness as a business rule, not a route.

The route must be able to answer even when opening a session is itself the
thing that fails, so the dependency graph for /ready stops at the session
*factory* rather than at a session. SQL stays in the repository: this service
asks the repository to ping.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.providers.cache import CacheProvider
from app.repositories.complaints import ComplaintRepository


@dataclass(frozen=True)
class ReadinessReport:
    ready: bool
    failed: str | None
    checks: dict[str, str]


class ReadinessService:
    def __init__(self, sessionmaker, cache: CacheProvider) -> None:
        self._sessionmaker = sessionmaker
        self._cache = cache

    async def check(self) -> ReadinessReport:
        checks: dict[str, str] = {}
        failed: str | None = None

        try:
            async with self._sessionmaker() as session:
                await ComplaintRepository(session).ping()
            checks["postgres"] = "ok"
        except Exception as exc:
            checks["postgres"] = f"unavailable: {type(exc).__name__}"
            failed = "postgres"

        try:
            await self._cache.ping()
            checks["redis"] = "ok"
        except Exception as exc:
            checks["redis"] = f"unavailable: {type(exc).__name__}"
            failed = failed or "redis"

        return ReadinessReport(ready=failed is None, failed=failed, checks=checks)
