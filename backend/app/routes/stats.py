"""Aggregate statistics, with the cache state exposed in a header."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.deps import get_stats_service
from app.schemas import StatsOut
from app.services.stats import StatsService

router = APIRouter(prefix="/api", tags=["stats"])


@router.get("/stats", response_model=StatsOut)
async def get_stats(
    response: Response, service: Annotated[StatsService, Depends(get_stats_service)]
) -> StatsOut:
    snapshot = await service.snapshot()
    response.headers["X-Cache"] = "HIT" if snapshot.cache_hit else "MISS"
    # Let the browser see a header it did not ask for: without this the
    # dashboard's fetch() cannot read X-Cache at all under CORS.
    response.headers["Access-Control-Expose-Headers"] = "X-Cache, X-Request-ID"
    return StatsOut.model_validate(snapshot.payload)
