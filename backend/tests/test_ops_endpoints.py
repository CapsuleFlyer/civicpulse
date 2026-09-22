"""Liveness, readiness and metrics."""

import pytest

from app.main import install_signal_handlers


class BrokenSessionmaker:
    def __call__(self, *args, **kwargs):
        raise ConnectionError("postgres is gone")


class BrokenCache:
    def key(self, *parts):
        return ":".join(parts)

    async def ping(self):
        raise ConnectionError("redis is gone")


@pytest.fixture
def break_postgres(client, monkeypatch):
    monkeypatch.setattr(client.app.state, "sessionmaker", BrokenSessionmaker())


@pytest.fixture
def break_redis(client, monkeypatch):
    monkeypatch.setattr(client.app.state, "cache", BrokenCache())


async def test_health_is_alive_without_touching_dependencies(
    client, break_postgres, break_redis
) -> None:
    # Both dependencies are broken. Liveness must not care: if it did, a slow
    # database would restart every pod in the deployment at once.
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_ready_is_200_when_dependencies_are_reachable(client) -> None:
    response = await client.get("/ready")
    assert response.status_code == 200
    assert response.json()["checks"] == {"postgres": "ok", "redis": "ok"}


async def test_ready_names_the_failed_dependency(client, break_redis) -> None:
    response = await client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["failed"] == "redis"
    assert "unavailable" in body["checks"]["redis"]


async def test_ready_names_postgres_when_the_database_is_unreachable(
    client, break_postgres
) -> None:
    response = await client.get("/ready")
    assert response.status_code == 503
    assert response.json()["failed"] == "postgres"


async def test_ready_reports_draining_after_sigterm(client) -> None:
    install_signal_handlers(client.app)
    client.app.state.draining = True
    response = await client.get("/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "draining"


async def test_metrics_exposes_prometheus_text(client) -> None:
    await client.get("/ready")
    response = await client.get("/metrics")
    assert response.status_code == 200
    assert "civicpulse_http_requests_total" in response.text
    assert "civicpulse_triage_duration_seconds" in response.text


async def test_request_id_is_echoed_back(client) -> None:
    response = await client.get("/health", headers={"X-Request-ID": "abc-123"})
    assert response.headers["X-Request-ID"] == "abc-123"
