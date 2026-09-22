"""Liveness, readiness and metrics.

/health and /ready are different questions, and Kubernetes acts on them
differently. Liveness failing restarts the pod; readiness failing only removes
it from the Service. So /health must never touch a dependency: if it did, a
slow database would restart every pod in the deployment at once, turning a
degraded system into an outage.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.config import Settings
from app.deps import get_readiness_service, get_settings_dep
from app.metrics import REGISTRY
from app.services.readiness import ReadinessService

router = APIRouter(tags=["ops"])


@router.get("/health")
async def health(request: Request, settings: Annotated[Settings, Depends(get_settings_dep)]) -> dict:
    """Process liveness. Deliberately dependency-free."""
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.git_sha,
        "draining": bool(getattr(request.app.state, "draining", False)),
    }


@router.get("/ready")
async def ready(
    request: Request,
    response: Response,
    readiness: Annotated[ReadinessService, Depends(get_readiness_service)],
) -> dict:
    """Readiness. 200 only if this pod can actually serve a request."""
    if getattr(request.app.state, "draining", False):
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "draining", "failed": "shutdown", "checks": {"process": "draining"}}

    report = await readiness.check()
    if not report.ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not_ready", "failed": report.failed, "checks": report.checks}
    return {"status": "ready", "checks": report.checks}


@router.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    return Response(content=generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
