"""Prometheus instrumentation.

Four series, each of which answers a question we actually ask during an
incident: how much traffic, how slow, how slow is the model, and how often is
the model letting us down.
"""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

REGISTRY = CollectorRegistry(auto_describe=True)

HTTP_REQUESTS = Counter(
    "civicpulse_http_requests_total",
    "HTTP requests by method, route template and status class.",
    ("method", "route", "status"),
    registry=REGISTRY,
)

HTTP_LATENCY = Histogram(
    "civicpulse_http_request_duration_seconds",
    "HTTP request latency.",
    ("method", "route"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=REGISTRY,
)

TRIAGE_LATENCY = Histogram(
    "civicpulse_triage_duration_seconds",
    "Time spent producing a triage result, by provider.",
    ("provider", "cached"),
    buckets=(0.001, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0),
    registry=REGISTRY,
)

TRIAGE_FALLBACKS = Counter(
    "civicpulse_triage_fallback_total",
    "Triage calls that fell back to the rule engine, by error class.",
    ("provider", "error"),
    registry=REGISTRY,
)

TRIAGE_CACHE = Counter(
    "civicpulse_triage_cache_total",
    "Triage content-hash cache lookups.",
    ("result",),
    registry=REGISTRY,
)

INFLIGHT = Gauge(
    "civicpulse_http_inflight_requests",
    "Requests currently being served. Watch this drain on SIGTERM.",
    registry=REGISTRY,
)
