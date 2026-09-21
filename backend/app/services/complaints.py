"""Complaint business rules: intake orchestration and the status machine."""

from __future__ import annotations

import logging
import uuid

from app.domain import Status, assert_can_transition
from app.models import Complaint
from app.repositories.complaints import ComplaintRepository
from app.schemas import ComplaintCreate
from app.services.stats import StatsService
from app.services.triage import TriageService

logger = logging.getLogger("civicpulse.complaints")


class ComplaintService:
    def __init__(
        self,
        repository: ComplaintRepository,
        triage: TriageService,
        stats: StatsService | None = None,
    ) -> None:
        self._repo = repository
        self._triage = triage
        # Stats are cached for 30s; a write invalidates them so the citizen who
        # just submitted a complaint sees the counter move immediately.
        self._stats = stats

    async def _invalidate_stats(self) -> None:
        if self._stats is not None:
            await self._stats.invalidate()

    async def submit(self, payload: ComplaintCreate) -> Complaint:
        outcome = await self._triage.triage(payload.text, payload.location)
        complaint = Complaint(
            id=uuid.uuid4(),
            text=payload.text,
            location=payload.location,
            reporter_contact=payload.reporter_contact,
            category=outcome.result.category,
            priority=outcome.result.priority,
            status=Status.OPEN,
            ai_summary=outcome.result.summary,
            triaged_by=outcome.provider,
            triage_latency_ms=outcome.latency_ms,
        )
        stored = await self._repo.add(complaint)
        await self._invalidate_stats()
        logger.info(
            "complaint_created",
            extra={
                "complaint_id": str(stored.id),
                "category": stored.category.value,
                "priority": stored.priority.value,
                "triaged_by": stored.triaged_by,
                "triage_latency_ms": stored.triage_latency_ms,
                "triage_cached": outcome.cached,
            },
        )
        if outcome.fallback:
            logger.warning(
                "complaint_triaged_by_fallback",
                extra={"complaint_id": str(stored.id), "provider": self._triage.provider_name},
            )
        return stored

    async def get(self, complaint_id: uuid.UUID) -> Complaint | None:
        return await self._repo.get(complaint_id)

    async def list_page(self, **kwargs) -> tuple[list[Complaint], int]:
        rows, total = await self._repo.list_page(**kwargs)
        return list(rows), total

    async def change_status(self, complaint: Complaint, requested: Status) -> Complaint:
        # Raises InvalidTransition, which the route turns into a 409 naming the
        # attempted transition. The table lives in domain.py; this line is the
        # only place it is enforced.
        assert_can_transition(complaint.status, requested)
        previous = complaint.status
        updated = await self._repo.update_status(complaint, requested)
        await self._invalidate_stats()
        logger.info(
            "complaint_status_changed",
            extra={
                "complaint_id": str(updated.id),
                "from": previous.value,
                "to": updated.status.value,
            },
        )
        return updated
