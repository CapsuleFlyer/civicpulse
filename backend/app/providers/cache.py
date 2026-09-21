"""Redis, doing two jobs.

Job 1 is a read-through cache (stats, and triage results keyed by content hash).
Job 2 is a distributed fixed-window rate limiter. They share one connection pool
because infrastructure is a capability, not a single-purpose box.

The limiter must live here rather than in a process dictionary: the moment the
HPA runs four backend pods, four in-process limiters permit four times the
configured traffic, which is the same as having no limiter at all.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any

from redis.asyncio import Redis

logger = logging.getLogger("civicpulse.cache")


@dataclass(frozen=True)
class RateLimitVerdict:
    allowed: bool
    remaining: int
    retry_after: int


def content_hash(*parts: str) -> str:
    joined = "\u241f".join(p.strip().lower() for p in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:32]


class CacheProvider:
    """Thin, typed wrapper. Nothing else in the app imports `redis` directly."""

    def __init__(self, redis: Redis, *, namespace: str = "civicpulse") -> None:
        self._redis = redis
        self._ns = namespace

    def key(self, *parts: str) -> str:
        return ":".join((self._ns, *parts))

    async def ping(self) -> bool:
        return bool(await self._redis.ping())

    async def get_json(self, key: str) -> Any | None:
        raw = await self._redis.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("cache_corrupt_entry", extra={"cache_key": key})
            await self._redis.delete(key)
            return None

    async def set_json(self, key: str, value: Any, ttl_seconds: int) -> None:
        await self._redis.set(key, json.dumps(value, default=str), ex=ttl_seconds)

    async def delete(self, *keys: str) -> None:
        if keys:
            await self._redis.delete(*keys)

    async def push_capped(self, key: str, value: Any, max_items: int) -> None:
        pipe = self._redis.pipeline()
        pipe.lpush(key, json.dumps(value, default=str))
        pipe.ltrim(key, 0, max_items - 1)
        await pipe.execute()

    async def recent(self, key: str, count: int) -> list[Any]:
        raw_items = await self._redis.lrange(key, 0, count - 1)
        out: list[Any] = []
        for raw in raw_items:
            try:
                out.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
        return out

    async def incr_counter(self, key: str) -> int:
        return int(await self._redis.incr(key))

    async def counters(self, *keys: str) -> list[int]:
        values = await self._redis.mget(*keys)
        return [int(v) if v is not None else 0 for v in values]

    async def check_rate_limit(self, identity: str, limit: int, window_seconds: int) -> RateLimitVerdict:
        """Fixed-window counter, keyed by client IP.

        INCR and TTL are pipelined so they travel as one round trip and run
        back-to-back on Redis' single command loop; the window's expiry is set
        only when the counter is created, which is what makes the window fixed
        rather than sliding forward on every request. A fixed window can let
        through up to 2x the limit across a boundary — accepted deliberately,
        because the job here is to stop a for-loop from burning the day's LLM
        quota, not to meter billing to the request.
        """
        key = self.key("ratelimit", identity)
        pipe = self._redis.pipeline()
        pipe.incr(key)
        pipe.ttl(key)
        current, ttl = await pipe.execute()
        current, ttl = int(current), int(ttl)
        if ttl < 0:
            await self._redis.expire(key, window_seconds)
            ttl = window_seconds
        retry_after = ttl if ttl > 0 else window_seconds
        return RateLimitVerdict(
            allowed=current <= limit,
            remaining=max(limit - current, 0),
            retry_after=retry_after,
        )
