"""Observability surface: which provider is live, and how it has been behaving."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.config import Settings
from app.deps import get_settings_dep, get_triage_service
from app.schemas import ProvidersOut, TriageOutcome
from app.services.triage import TriageService

router = APIRouter(prefix="/api/meta", tags=["meta"])


@router.get("/providers", response_model=ProvidersOut)
async def providers(
    triage: Annotated[TriageService, Depends(get_triage_service)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> ProvidersOut:
    recent = await triage.history(settings.meta_history_size)
    return ProvidersOut(
        active_provider=triage.provider_name,
        configured=settings.triage_provider,
        fallback_provider=triage.fallback_name,
        triage_cache_hit_rate=await triage.cache_hit_rate(),
        recent=[TriageOutcome.model_validate(item) for item in recent],
    )
