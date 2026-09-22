"""Redis doing both of its jobs."""

from tests.conftest import VALID_COMPLAINT


async def test_stats_are_a_miss_then_a_hit(client) -> None:
    first = await client.get("/api/stats")
    assert first.headers["X-Cache"] == "MISS"
    second = await client.get("/api/stats")
    assert second.headers["X-Cache"] == "HIT"
    assert first.json() == second.json()


async def test_a_write_invalidates_the_stats_cache(client) -> None:
    await client.get("/api/stats")
    assert (await client.get("/api/stats")).headers["X-Cache"] == "HIT"

    await client.post("/api/complaints", json=VALID_COMPLAINT)

    refreshed = await client.get("/api/stats")
    assert refreshed.headers["X-Cache"] == "MISS", "a new complaint must appear immediately"
    assert refreshed.json()["total"] == 1


async def test_a_status_change_also_invalidates_the_stats_cache(client) -> None:
    created = (await client.post("/api/complaints", json=VALID_COMPLAINT)).json()
    await client.get("/api/stats")
    await client.patch(f"/api/complaints/{created['id']}/status", json={"status": "in_progress"})

    refreshed = await client.get("/api/stats")
    assert refreshed.headers["X-Cache"] == "MISS"
    assert refreshed.json()["by_status"]["in_progress"] == 1


async def test_stats_shape_covers_every_enum_member(client) -> None:
    body = (await client.get("/api/stats")).json()
    assert set(body["by_category"]) == {
        "water", "electricity", "sanitation", "roads", "streetlights", "other"
    }
    assert set(body["by_priority"]) == {"high", "normal", "low"}
    assert set(body["by_status"]) == {"open", "in_progress", "resolved", "rejected"}
    assert body["fallback_rate"] == 0.0


async def test_rate_limiter_returns_429_with_retry_after(client_factory) -> None:
    client = await client_factory(rate_limit_requests=3, rate_limit_window_seconds=60)

    for attempt in range(3):
        response = await client.post(
            "/api/complaints",
            json={**VALID_COMPLAINT, "text": f"Water supply has been off for {attempt} days now."},
        )
        assert response.status_code == 201

    blocked = await client.post("/api/complaints", json=VALID_COMPLAINT)
    assert blocked.status_code == 429
    assert blocked.json()["error"] == "rate_limited"
    retry_after = int(blocked.headers["Retry-After"])
    assert 0 < retry_after <= 60


async def test_rate_limit_buckets_are_per_client(client_factory) -> None:
    client = await client_factory(rate_limit_requests=1, rate_limit_window_seconds=60)
    first = await client.post(
        "/api/complaints", json=VALID_COMPLAINT, headers={"X-Forwarded-For": "10.0.0.1"}
    )
    same_ip = await client.post(
        "/api/complaints", json=VALID_COMPLAINT, headers={"X-Forwarded-For": "10.0.0.1"}
    )
    other_ip = await client.post(
        "/api/complaints", json=VALID_COMPLAINT, headers={"X-Forwarded-For": "10.0.0.2"}
    )
    assert first.status_code == 201
    assert same_ip.status_code == 429
    assert other_ip.status_code == 201, "one noisy caller must not block the city"


async def test_reads_are_not_rate_limited(client_factory) -> None:
    client = await client_factory(rate_limit_requests=1)
    await client.post("/api/complaints", json=VALID_COMPLAINT)
    for _ in range(5):
        assert (await client.get("/api/complaints")).status_code == 200
