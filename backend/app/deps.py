"""Composition root for HTTP requests.

Routes depend on *services*, never on a session, a repository or a Redis
handle. This module is the only place where a request-scoped session is opened
and wired into a service, which is why `routes/` contains no persistence code
to accidentally grow business rules around.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.errors import rate_limited
from app.providers.cache import CacheProvider
from app.repositories.complaints import ComplaintRepository
from app.services.complaints import ComplaintService
from app.services.readiness import ReadinessService
from app.services.stats import StatsService
from app.services.triage import TriageService


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_cache(request: Request) -> CacheProvider:
    return request.app.state.cache


def get_triage_service(request: Request) -> TriageService:
    return request.app.state.triage_service


async def _session(request: Request) -> AsyncIterator[AsyncSession]:
    factory = request.app.state.sessionmaker
    async with factory() as session:
        yield session


async def get_complaint_service(
    session: Annotated[AsyncSession, Depends(_session)],
    triage: Annotated[TriageService, Depends(get_triage_service)],
    cache: Annotated[CacheProvider, Depends(get_cache)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> ComplaintService:
    repository = ComplaintRepository(session)
    return ComplaintService(repository, triage, StatsService(repository, cache, settings))


async def get_stats_service(
    session: Annotated[AsyncSession, Depends(_session)],
    cache: Annotated[CacheProvider, Depends(get_cache)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> StatsService:
    return StatsService(ComplaintRepository(session), cache, settings)


def get_readiness_service(request: Request) -> ReadinessService:
    # Note the sessionmaker, not a session: /ready must be able to report that
    # the database is unreachable, which it could not do if acquiring a
    # connection were a precondition of the route running at all.
    return ReadinessService(request.app.state.sessionmaker, request.app.state.cache)


def client_identity(request: Request) -> str:
    """Rate-limit identity.

    X-Forwarded-For first, because behind an Ingress every request appears to
    come from the ingress controller's pod IP and one limiter bucket would be
    shared by the entire city.
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def enforce_rate_limit(
    request: Request,
    cache: Annotated[CacheProvider, Depends(get_cache)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> None:
    verdict = await cache.check_rate_limit(
        client_identity(request), settings.rate_limit_requests, settings.rate_limit_window_seconds
    )
    if not verdict.allowed:
        raise rate_limited(
            verdict.retry_after, settings.rate_limit_requests, settings.rate_limit_window_seconds
        )
