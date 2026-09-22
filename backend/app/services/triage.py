"""Everything that makes an unreliable third party safe to depend on.

Calling a model is four lines. This file is the assignment: timeout, one
jittered retry on retryable errors only, content-hash caching, a fallback that
can never fail, and enough measurement to argue about cost afterwards.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from app.config import Settings
from app.metrics import TRIAGE_CACHE, TRIAGE_FALLBACKS, TRIAGE_LATENCY
from app.providers.cache import CacheProvider, content_hash
from app.providers.triage.base import TriageError, TriageProvider, TriageResult
from app.providers.triage.rules import RuleBasedTriage

logger = logging.getLogger("civicpulse.triage")

CACHE_HITS_KEY = "triage:cache:hits"
CACHE_MISSES_KEY = "triage:cache:misses"
HISTORY_KEY = "triage:history"


@dataclass(frozen=True)
class TriageOutcome:
    result: TriageResult
    provider: str
    latency_ms: int
    fallback: bool
    cached: bool


class TriageService:
    def __init__(
        self,
        *,
        provider: TriageProvider,
        cache: CacheProvider,
        settings: Settings,
        fallback: TriageProvider | None = None,
    ) -> None:
        self._provider = provider
        self._cache = cache
        self._settings = settings
        self._fallback = fallback or RuleBasedTriage()

    @property
    def provider_name(self) -> str:
        return self._provider.name

    @property
    def fallback_name(self) -> str:
        return self._fallback.name

    # --- public ---------------------------------------------------------

    async def triage(self, text: str, location: str) -> TriageOutcome:
        started = time.perf_counter()
        cache_key = self._cache.key("triage", content_hash(text, location))

        cached = await self._read_cache(cache_key)
        if cached is not None:
            latency_ms = int((time.perf_counter() - started) * 1000)
            TRIAGE_LATENCY.labels(cached.provider, "true").observe(time.perf_counter() - started)
            outcome = TriageOutcome(
                result=cached.result,
                provider=cached.provider,
                latency_ms=latency_ms,
                fallback=cached.fallback,
                cached=True,
            )
            await self._record(outcome)
            return outcome

        outcome = await self._call_with_policy(text, location, started)
        # Fallback results are deliberately not cached for 24h: the next request
        # should get a fresh attempt at the real provider once it recovers.
        if not outcome.fallback:
            await self._write_cache(cache_key, outcome)
        await self._record(outcome)
        return outcome

    async def history(self, count: int) -> list[dict]:
        return await self._cache.recent(self._cache.key(HISTORY_KEY), count)

    async def cache_hit_rate(self) -> float:
        hits, misses = await self._cache.counters(
            self._cache.key(CACHE_HITS_KEY), self._cache.key(CACHE_MISSES_KEY)
        )
        total = hits + misses
        return round(hits / total, 4) if total else 0.0

    # --- policy ---------------------------------------------------------

    async def _call_with_policy(self, text: str, location: str, started: float) -> TriageOutcome:
        attempts = self._settings.triage_max_retries + 1
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                result = await asyncio.wait_for(
                    self._provider.triage(text, location),
                    timeout=self._settings.triage_timeout_seconds,
                )
                elapsed = time.perf_counter() - started
                TRIAGE_LATENCY.labels(self._provider.name, "false").observe(elapsed)
                return TriageOutcome(
                    result=result,
                    provider=self._provider.name,
                    latency_ms=int(elapsed * 1000),
                    fallback=False,
                    cached=False,
                )
            except (TimeoutError, TriageError) as exc:
                last_error = exc
                retryable = getattr(exc, "retryable", isinstance(exc, asyncio.TimeoutError))
                if retryable and attempt < attempts:
                    # Jitter, so that a provider recovering from an outage is not
                    # hit by every one of our pods at the same millisecond.
                    delay = random.uniform(0.1, 0.4) * attempt
                    logger.warning(
                        "triage_retry",
                        extra={
                            "provider": self._provider.name,
                            "attempt": attempt,
                            "error_class": type(exc).__name__,
                            "retry_in_ms": int(delay * 1000),
                        },
                    )
                    await asyncio.sleep(delay)
                    continue
                break
            except Exception as exc:  # defensive: a provider bug is not a 500
                last_error = exc
                break

        return await self._degrade(text, location, started, last_error)

    async def _degrade(
        self, text: str, location: str, started: float, error: Exception | None
    ) -> TriageOutcome:
        error_class = type(error).__name__ if error else "UnknownError"
        TRIAGE_FALLBACKS.labels(self._provider.name, error_class).inc()
        logger.warning(
            "triage_fallback",
            extra={
                "provider": self._provider.name,
                "fallback_provider": self._fallback.name,
                "error_class": error_class,
                "error_message": str(error) if error else "",
            },
        )
        result = await self._fallback.triage(text, location)
        elapsed = time.perf_counter() - started
        TRIAGE_LATENCY.labels("rules:fallback", "false").observe(elapsed)
        return TriageOutcome(
            result=result,
            provider="rules:fallback",
            latency_ms=int(elapsed * 1000),
            fallback=True,
            cached=False,
        )

    # --- cache ----------------------------------------------------------

    async def _read_cache(self, key: str) -> TriageOutcome | None:
        try:
            payload = await self._cache.get_json(key)
        except Exception:  # a cache outage must not become a user-visible error
            logger.warning("triage_cache_unavailable", exc_info=True)
            return None
        if not payload:
            TRIAGE_CACHE.labels("miss").inc()
            await self._safe_incr(CACHE_MISSES_KEY)
            return None
        try:
            result = TriageResult.model_validate(payload["result"])
        except Exception:
            return None
        TRIAGE_CACHE.labels("hit").inc()
        await self._safe_incr(CACHE_HITS_KEY)
        return TriageOutcome(
            result=result,
            provider=payload.get("provider", "unknown"),
            latency_ms=0,
            fallback=bool(payload.get("fallback", False)),
            cached=True,
        )

    async def _write_cache(self, key: str, outcome: TriageOutcome) -> None:
        try:
            await self._cache.set_json(
                key,
                {
                    "result": outcome.result.model_dump(mode="json"),
                    "provider": outcome.provider,
                    "fallback": outcome.fallback,
                },
                self._settings.triage_cache_ttl_seconds,
            )
        except Exception:
            logger.warning("triage_cache_write_failed", exc_info=True)

    async def _safe_incr(self, key: str) -> None:
        # A hit-rate counter is not worth failing a citizen's submission for.
        try:
            await self._cache.incr_counter(self._cache.key(key))
        except Exception:
            logger.debug("triage_cache_counter_failed", exc_info=True)

    async def _record(self, outcome: TriageOutcome) -> None:
        try:
            await self._cache.push_capped(
                self._cache.key(HISTORY_KEY),
                {
                    "provider": outcome.provider,
                    "latency_ms": outcome.latency_ms,
                    "fallback": outcome.fallback,
                    "cached": outcome.cached,
                    "at": datetime.now(UTC).isoformat(timespec="seconds"),
                },
                self._settings.meta_history_size,
            )
        except Exception:
            logger.warning("triage_history_write_failed", exc_info=True)
