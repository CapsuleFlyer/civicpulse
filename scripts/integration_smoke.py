#!/usr/bin/env python3
"""End-to-end smoke test against a running CivicPulse stack.

Used by two jobs:

  * ci.yml `integration` — against `docker compose up -d` on the runner
  * cd.yml `deploy-k8s`  — against the Ingress on an ephemeral k3d cluster

It asserts the request path a citizen actually takes, not that a process is
listening: readiness, a POST that comes back triaged, a GET that returns the
same row, the state machine rejecting an illegal transition with 409, and the
stats cache going MISS then HIT.

Standard library only — the runner should not need a pip install to smoke a
deployment.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any

TIMEOUT = 15


class SmokeFailure(AssertionError):
    pass


def request(
    method: str,
    url: str,
    *,
    body: dict[str, Any] | None = None,
    host: str | None = None,
) -> tuple[int, dict[str, str], Any]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if host:
        req.add_header("Host", host)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read().decode("utf-8")
            headers = {k.lower(): v for k, v in resp.headers.items()}
            status = resp.status
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        headers = {k.lower(): v for k, v in exc.headers.items()}
        status = exc.code
    except urllib.error.URLError as exc:
        raise SmokeFailure(f"{method} {url} did not connect: {exc.reason}") from exc

    try:
        parsed = json.loads(raw) if raw else None
    except json.JSONDecodeError:
        parsed = raw
    return status, headers, parsed


def step(label: str) -> None:
    print(f"\n--> {label}", flush=True)


def wait_for_ready(base: str, host: str | None, attempts: int = 60) -> None:
    step(f"waiting for {base}/ready")
    last = ""
    for attempt in range(1, attempts + 1):
        try:
            status, _, payload = request("GET", f"{base}/ready", host=host)
        except SmokeFailure as exc:
            last = str(exc)
        else:
            if status == 200:
                print(f"    ready after {attempt} attempt(s): {payload}")
                return
            last = f"HTTP {status}: {payload}"
        time.sleep(2)
    raise SmokeFailure(f"/ready never returned 200. Last response: {last}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="e.g. http://localhost:8000")
    parser.add_argument(
        "--host",
        default=None,
        help="Host header to send, for Ingress-routed clusters",
    )
    parser.add_argument(
        "--api-prefix",
        default="/api",
        help="prefix the API is mounted under (default: /api)",
    )
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    api = f"{base}{args.api_prefix}"
    host = args.host

    wait_for_ready(base, host)

    step("GET /health must not touch the database")
    status, _, payload = request("GET", f"{base}/health", host=host)
    if status != 200:
        raise SmokeFailure(f"/health returned {status}: {payload}")
    print(f"    {payload}")

    step("POST /api/complaints — a burst main, which must triage as high priority water")
    complaint = {
        "text": (
            "Burst water main in Street 12 since fajr time, water is entering the "
            "ground floor of three houses and the road is fully flooded. Kindly send "
            "team urgently before more damage happens."
        ),
        "location": "Street 12, Sector G-9/3, Islamabad",
        "reporter_contact": "+92 300 1234567",
    }
    status, _, created = request("POST", f"{api}/complaints", body=complaint, host=host)
    if status != 201:
        raise SmokeFailure(f"POST /api/complaints returned {status}: {created}")
    for field in (
        "id",
        "category",
        "priority",
        "status",
        "ai_summary",
        "triaged_by",
        "triage_latency_ms",
    ):
        if field not in created:
            raise SmokeFailure(f"created complaint has no '{field}': {created}")
    if created["category"] != "water":
        raise SmokeFailure(
            f"expected category 'water' for a burst main, got {created['category']!r}. "
            "Check the rules provider keyword table and the triage prompt."
        )
    if created["status"] != "open":
        raise SmokeFailure(f"new complaints must start 'open', got {created['status']!r}")
    if len(created["ai_summary"] or "") > 140:
        raise SmokeFailure("ai_summary exceeded 140 characters — schema validation failed")
    complaint_id = created["id"]
    print(
        f"    id={complaint_id} category={created['category']} "
        f"priority={created['priority']} triaged_by={created['triaged_by']} "
        f"latency={created['triage_latency_ms']}ms"
    )

    step("GET /api/complaints/{id} — the row comes back identically")
    status, _, fetched = request("GET", f"{api}/complaints/{complaint_id}", host=host)
    if status != 200:
        raise SmokeFailure(f"GET by id returned {status}: {fetched}")
    if fetched["id"] != complaint_id or fetched["category"] != created["category"]:
        raise SmokeFailure("GET by id returned a different row than POST created")
    print("    round trip matches")

    step("GET /api/complaints/{unknown} — 404")
    status, _, payload = request(
        "GET", f"{api}/complaints/00000000-0000-0000-0000-000000000000", host=host
    )
    if status != 404:
        raise SmokeFailure(f"unknown id returned {status}, expected 404: {payload}")

    step("GET /api/complaints — filters and pagination")
    status, _, page = request(
        "GET", f"{api}/complaints?status=open&page=1&page_size=5", host=host
    )
    if status != 200:
        raise SmokeFailure(f"list returned {status}: {page}")
    for field in ("items", "total", "page", "page_size"):
        if field not in page:
            raise SmokeFailure(f"list response has no '{field}': {page}")
    if len(page["items"]) > 5:
        raise SmokeFailure("page_size was not honoured")
    if any(item["status"] != "open" for item in page["items"]):
        raise SmokeFailure("status filter leaked non-open rows")
    print(f"    total={page['total']} returned={len(page['items'])}")

    step("PATCH status — legal transition open -> in_progress")
    status, _, moved = request(
        "PATCH",
        f"{api}/complaints/{complaint_id}/status",
        body={"status": "in_progress"},
        host=host,
    )
    if status != 200:
        raise SmokeFailure(f"legal transition returned {status}: {moved}")
    if moved["status"] != "in_progress":
        raise SmokeFailure(f"status did not move: {moved}")

    step("PATCH status — illegal transition in_progress -> open must be 409 and name it")
    status, _, conflict = request(
        "PATCH",
        f"{api}/complaints/{complaint_id}/status",
        body={"status": "open"},
        host=host,
    )
    if status != 409:
        raise SmokeFailure(f"illegal transition returned {status}, expected 409: {conflict}")
    message = json.dumps(conflict)
    if "in_progress" not in message or "open" not in message:
        raise SmokeFailure(
            f"409 body must name the attempted transition, got: {message}"
        )
    print(f"    {message[:160]}")

    step("GET /api/stats — X-Cache must go MISS then HIT")
    status, headers, stats = request("GET", f"{api}/stats", host=host)
    if status != 200:
        raise SmokeFailure(f"stats returned {status}: {stats}")
    first = headers.get("x-cache", "")
    if first != "MISS":
        raise SmokeFailure(
            f"first /api/stats after a write must be a MISS (write invalidates the "
            f"cache), got {first!r}"
        )
    status, headers, stats_again = request("GET", f"{api}/stats", host=host)
    second = headers.get("x-cache", "")
    if second != "HIT":
        raise SmokeFailure(f"second /api/stats must be a HIT, got {second!r}")
    if stats != stats_again:
        raise SmokeFailure("cached stats payload differs from the uncached one")
    if "by_category" not in stats or "by_priority" not in stats:
        raise SmokeFailure(f"stats payload is missing aggregates: {stats}")
    print(f"    MISS -> HIT, total={stats.get('total')}")

    step("POST a complaint — stats cache must be invalidated on write, not left to TTL")
    request("POST", f"{api}/complaints", body=complaint, host=host)
    _, headers, _ = request("GET", f"{api}/stats", host=host)
    if headers.get("x-cache") != "MISS":
        raise SmokeFailure(
            "a write did not invalidate the stats cache — the dashboard would show "
            "stale aggregates for up to 30 seconds"
        )
    print("    write invalidated the cache")

    step("GET /api/meta/providers — the observability surface")
    status, _, meta = request("GET", f"{api}/meta/providers", host=host)
    if status != 200:
        raise SmokeFailure(f"meta returned {status}: {meta}")
    if "active_provider" not in meta or "recent" not in meta:
        raise SmokeFailure(f"meta payload is incomplete: {meta}")
    if not meta["recent"]:
        raise SmokeFailure("no recent triage outcomes recorded after two POSTs")
    if len(meta["recent"]) > 20:
        raise SmokeFailure("meta/providers must cap the window at the last 20 outcomes")
    sample = meta["recent"][0]
    for field in ("provider", "latency_ms", "fallback"):
        if field not in sample:
            raise SmokeFailure(f"recent triage outcome has no '{field}': {sample}")
    print(f"    active={meta['active_provider']} recent={len(meta['recent'])}")

    step("GET /metrics — Prometheus text format")
    status, headers, body = request("GET", f"{base}/metrics", host=host)
    if status != 200:
        raise SmokeFailure(f"/metrics returned {status}")
    text = body if isinstance(body, str) else json.dumps(body)
    for metric in (
        "civicpulse_http_requests_total",
        "civicpulse_http_request_duration_seconds",
        "civicpulse_triage_latency_seconds",
        "civicpulse_triage_fallbacks_total",
    ):
        if metric not in text:
            raise SmokeFailure(f"/metrics does not expose {metric}")
    print("    all four required metric families present")

    step("POST with a too-short text — 400 with a field-level error body")
    status, _, invalid = request(
        "POST",
        f"{api}/complaints",
        body={"text": "short", "location": "G-9"},
        host=host,
    )
    if status not in (400, 422):
        raise SmokeFailure(f"invalid payload returned {status}: {invalid}")
    blob = json.dumps(invalid)
    if "text" not in blob:
        raise SmokeFailure(f"validation error is not field-level: {blob}")
    print(f"    {blob[:140]}")

    print("\nAll smoke checks passed.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SmokeFailure as exc:
        print(f"\nSMOKE FAILURE: {exc}", file=sys.stderr)
        sys.exit(1)
