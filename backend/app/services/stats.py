"""Aggregate statistics, read through Redis.

TTL *and* explicit invalidation, deliberately. The TTL bounds staleness for
things this service does not observe — a row changed by another replica, a
manual fix in psql, a backfill job. Invalidation gives the citizen who just
submitted a complaint the satisfaction of seeing the counter move. Either alone
is defensible; together they cover both the writes we know about and the ones
we do not.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.config import Settings
from app.providers.cache import CacheProvider
from app.repositories.complaints import ComplaintRepository

STATS_KEY = "stats:v1"


@dataclass(frozen=True)
class StatsSnapshot:
    payload: dict
    cache_hit: bool


class StatsService:
    def __init__(
        self, repository: ComplaintRepository, cache: CacheProvider, settings: Settings
    ) -> None:
        self._repo = repository
        self._cache = cache
        self._settings = settings

    @property
    def _key(self) -> str:
        return self._cache.key(STATS_KEY)

    async def snapshot(self) -> StatsSnapshot:
        cached = await self._cache.get_json(self._key)
        if cached:
            return StatsSnapshot(payload=cached, cache_hit=True)

        aggregates = await self._repo.aggregate()
        payload = {
            **aggregates,
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        await self._cache.set_json(self._key, payload, self._settings.stats_cache_ttl_seconds)
        return StatsSnapshot(payload=payload, cache_hit=False)

    async def invalidate(self) -> None:
        await self._cache.delete(self._key)
