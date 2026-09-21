"""Complaint endpoints. No SQL, no business rules — orchestration lives in services/."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.deps import enforce_rate_limit, get_complaint_service
from app.domain import Category, InvalidTransition, Priority, Status
from app.errors import conflict_from_transition, not_found
from app.schemas import ComplaintCreate, ComplaintOut, Page, StatusPatch
from app.services.complaints import ComplaintService

router = APIRouter(prefix="/api/complaints", tags=["complaints"])

ServiceDep = Annotated[ComplaintService, Depends(get_complaint_service)]


@router.post(
    "",
    response_model=ComplaintOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(enforce_rate_limit)],
    responses={400: {"description": "field-level validation errors"}, 429: {"description": "rate limited"}},
)
async def create_complaint(
    payload: ComplaintCreate, service: ServiceDep, response: Response
) -> ComplaintOut:
    complaint = await service.submit(payload)
    response.headers["Location"] = f"/api/complaints/{complaint.id}"
    return ComplaintOut.model_validate(complaint)


@router.get("", response_model=Page[ComplaintOut])
async def list_complaints(
    service: ServiceDep,
    category: Category | None = None,
    priority: Priority | None = None,
    complaint_status: Annotated[Status | None, Query(alias="status")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[ComplaintOut]:
    rows, total = await service.list_page(
        page=page,
        page_size=page_size,
        category=category,
        priority=priority,
        status=complaint_status,
    )
    return Page[ComplaintOut](
        items=[ComplaintOut.model_validate(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{complaint_id}", response_model=ComplaintOut)
async def get_complaint(complaint_id: uuid.UUID, service: ServiceDep) -> ComplaintOut:
    complaint = await service.get(complaint_id)
    if complaint is None:
        raise not_found("complaint", complaint_id)
    return ComplaintOut.model_validate(complaint)


@router.patch("/{complaint_id}/status", response_model=ComplaintOut)
async def patch_status(
    complaint_id: uuid.UUID, payload: StatusPatch, service: ServiceDep
) -> ComplaintOut:
    complaint = await service.get(complaint_id)
    if complaint is None:
        raise not_found("complaint", complaint_id)
    try:
        updated = await service.change_status(complaint, payload.status)
    except InvalidTransition as exc:
        raise conflict_from_transition(exc) from exc
    return ComplaintOut.model_validate(updated)
