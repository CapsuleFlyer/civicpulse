"""Deterministic keyword triage.

This provider is the floor of the system: no network, no key, no quota, and no
way to fail. It is both a first-class choice (TRIAGE_PROVIDER=rules) and the
fallback every other provider degrades to.
"""

from __future__ import annotations

from app.domain import Category, Priority
from app.providers.triage.base import TriageResult

CATEGORY_KEYWORDS: dict[Category, tuple[str, ...]] = {
    Category.WATER: (
        "water", "pani", "burst main", "water main", "leak", "leakage", "sewer line",
        "pipeline", "tap", "boring", "tanker", "flooding", "drinking water",
    ),
    Category.ELECTRICITY: (
        "electric", "electricity", "bijli", "power", "load shedding", "loadshedding",
        "transformer", "pmt", "wire", "wapda", "iesco", "k-electric", "outage", "voltage",
    ),
    Category.SANITATION: (
        "garbage", "kachra", "trash", "rubbish", "sewerage", "sewage", "gutter", "drain",
        "manhole", "sanitation", "sweeper", "dump", "stench", "smell", "mosquito",
    ),
    Category.ROADS: (
        "road", "sarak", "pothole", "potholes", "footpath", "speed breaker", "manhole cover",
        "traffic signal", "signal", "underpass", "encroachment", "gully",
    ),
    Category.STREETLIGHTS: (
        "streetlight", "street light", "street lamp", "lamp post", "pole light", "dark street",
        "lights not working", "lighting",
    ),
}

HIGH_PRIORITY_MARKERS: tuple[str, ...] = (
    "burst", "flood", "flooding", "fire", "spark", "sparking", "live wire", "electrocut",
    "collapse", "collapsed", "sinkhole", "open manhole", "child", "children", "school",
    "hospital", "clinic", "injur", "accident", "dangerous", "emergency", "overflow",
    "contaminated", "gas", "days without", "no water since", "elderly",
)

LOW_PRIORITY_MARKERS: tuple[str, ...] = (
    "paint", "faded", "cosmetic", "slightly", "minor", "request", "suggest", "would be nice",
    "please consider", "dusty", "untidy", "noise at night",
)


def _score_category(haystack: str) -> tuple[Category, int]:
    best, best_hits = Category.OTHER, 0
    for category, keywords in CATEGORY_KEYWORDS.items():
        hits = sum(1 for keyword in keywords if keyword in haystack)
        if hits > best_hits:
            best, best_hits = category, hits
    return best, best_hits


def _score_priority(haystack: str) -> Priority:
    if any(marker in haystack for marker in HIGH_PRIORITY_MARKERS):
        return Priority.HIGH
    if any(marker in haystack for marker in LOW_PRIORITY_MARKERS):
        return Priority.LOW
    return Priority.NORMAL


def summarise(text: str, location: str, category: Category) -> str:
    condensed = " ".join(text.split())
    head = condensed[:90].rstrip(" ,.;:")
    if len(condensed) > 90:
        head += "…"
    line = f"{category.value.capitalize()} issue at {location}: {head}"
    return line[:140]


class RuleBasedTriage:
    name = "rules"

    async def triage(self, text: str, location: str) -> TriageResult:
        haystack = f"{text} {location}".lower()
        category, hits = _score_category(haystack)
        priority = _score_priority(haystack)
        # Confidence is keyword density, not a guess dressed as a number. It is
        # deliberately capped below the LLM path so an operator sorting by
        # confidence can see which rows a machine actually read.
        confidence = 0.25 if hits == 0 else min(0.35 + 0.1 * hits, 0.7)
        return TriageResult(
            category=category,
            priority=priority,
            summary=summarise(text, location, category),
            confidence=round(confidence, 2),
        )
