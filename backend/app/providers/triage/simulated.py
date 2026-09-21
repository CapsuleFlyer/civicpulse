"""Deterministic fake used by CI.

Seeded, no network, and able to fail on demand. This is how the pipeline stays
green on every run while still exercising the code paths that only appear when
a real provider misbehaves.
"""

from __future__ import annotations

import asyncio
import hashlib

from app.domain import Category, Priority
from app.providers.triage.base import (
    TriageResult,
    TriageTimeout,
    TriageUpstreamError,
    parse_triage_payload,
)
from app.providers.triage.prompt import sanitize

_CATEGORIES = list(Category)
_PRIORITIES = list(Priority)


class SimulatedTriage:
    name = "llm:simulated"

    def __init__(
        self,
        *,
        seed: int = 1337,
        failure_mode: str = "none",
        latency_ms: int = 5,
    ) -> None:
        self._seed = seed
        self._failure_mode = failure_mode
        self._latency_ms = latency_ms

    def _digest(self, text: str, location: str) -> int:
        payload = f"{self._seed}|{text.strip().lower()}|{location.strip().lower()}"
        return int(hashlib.sha256(payload.encode()).hexdigest(), 16)

    async def triage(self, text: str, location: str) -> TriageResult:
        if self._latency_ms:
            await asyncio.sleep(self._latency_ms / 1000)
        if self._failure_mode == "raise":
            raise TriageUpstreamError("simulated provider failure")
        if self._failure_mode == "timeout":
            raise TriageTimeout("simulated provider timeout")
        if self._failure_mode == "malformed":
            # Goes through the same parser a real model's prose would hit.
            return parse_triage_payload("Sure! Here is the triage: category=urgent-water")

        digest = self._digest(text, location)
        category = _CATEGORIES[digest % len(_CATEGORIES)]
        priority = _PRIORITIES[(digest // 7) % len(_PRIORITIES)]
        summary = f"[simulated] {sanitize(text, limit=100)}"[:140]
        confidence = round(0.55 + (digest % 40) / 100, 2)
        return TriageResult(
            category=category, priority=priority, summary=summary, confidence=confidence
        )
