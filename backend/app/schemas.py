"""HTTP data-transfer objects.

Pydantic is used twice in this codebase with one mental model: here for HTTP
input and output, and in `providers/triage/base.py` for LLM output. The model
does not get to be trusted more than the citizen does.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from app.domain import Category, Priority, Status

T = TypeVar("T")


class ComplaintCreate(BaseModel):
    text: str = Field(min_length=10, max_length=2000)
    location: str = Field(min_length=3, max_length=200)
    reporter_contact: str | None = Field(default=None, max_length=120)


class StatusPatch(BaseModel):
    status: Status


class ComplaintOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    text: str
    location: str
    reporter_contact: str | None
    category: Category
    priority: Priority
    status: Status
    ai_summary: str | None
    triaged_by: str
    triage_latency_ms: int
    created_at: datetime
    updated_at: datetime


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class StatsOut(BaseModel):
    total: int
    by_category: dict[str, int]
    by_priority: dict[str, int]
    by_status: dict[str, int]
    fallback_rate: float = Field(ge=0.0, le=1.0)
    generated_at: datetime


class TriageOutcome(BaseModel):
    provider: str
    latency_ms: int
    fallback: bool
    cached: bool
    complaint_id: str | None = None
    at: datetime


class ProvidersOut(BaseModel):
    active_provider: str
    configured: str
    fallback_provider: str
    triage_cache_hit_rate: float
    recent: list[TriageOutcome]


class FieldError(BaseModel):
    field: str
    message: str


class ValidationErrorOut(BaseModel):
    error: str = "validation_error"
    message: str
    fields: list[FieldError]
