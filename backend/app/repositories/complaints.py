"""The only module in the application that writes SQL.

Services ask for domain objects; they never see a Select, a session, or a
dialect. That boundary is what makes the service layer testable without a
database and the database replaceable without touching business rules.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import Category, Priority, Status
from app.models import Complaint


class ComplaintRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- writes ---------------------------------------------------------

    async def add(self, complaint: Complaint) -> Complaint:
        self._session.add(complaint)
        await self._session.commit()
        await self._session.refresh(complaint)
        return complaint

    async def update_status(self, complaint: Complaint, status: Status) -> Complaint:
        complaint.status = status
        complaint.updated_at = datetime.now(UTC)
        await self._session.commit()
        await self._session.refresh(complaint)
        return complaint

    async def exists(self, complaint_id: uuid.UUID) -> bool:
        stmt = select(func.count()).select_from(Complaint).where(Complaint.id == complaint_id)
        return bool((await self._session.execute(stmt)).scalar_one())

    # --- reads ----------------------------------------------------------

    async def get(self, complaint_id: uuid.UUID) -> Complaint | None:
        return await self._session.get(Complaint, complaint_id)

    def _filtered(
        self,
        stmt: Select,
        category: Category | None,
        priority: Priority | None,
        status: Status | None,
    ) -> Select:
        if category is not None:
            stmt = stmt.where(Complaint.category == category)
        if priority is not None:
            stmt = stmt.where(Complaint.priority == priority)
        if status is not None:
            stmt = stmt.where(Complaint.status == status)
        return stmt

    async def list_page(
        self,
        *,
        page: int,
        page_size: int,
        category: Category | None = None,
        priority: Priority | None = None,
        status: Status | None = None,
    ) -> tuple[Sequence[Complaint], int]:
        # Covered by ix_complaints_status_priority when the operator filters the
        # queue, and by ix_complaints_created_at for the ORDER BY below.
        rows_stmt = self._filtered(select(Complaint), category, priority, status)
        rows_stmt = rows_stmt.order_by(Complaint.created_at.desc()).offset(
            (page - 1) * page_size
        ).limit(page_size)
        count_stmt = self._filtered(
            select(func.count()).select_from(Complaint), category, priority, status
        )
        rows = (await self._session.execute(rows_stmt)).scalars().all()
        total = int((await self._session.execute(count_stmt)).scalar_one())
        return rows, total

    async def _group_count(self, column) -> dict[str, int]:
        stmt = select(column, func.count()).group_by(column)
        result = await self._session.execute(stmt)
        out: dict[str, int] = {}
        for value, count in result.all():
            key = value.value if hasattr(value, "value") else str(value)
            out[key] = int(count)
        return out

    async def aggregate(self) -> dict[str, object]:
        total = int((await self._session.execute(select(func.count()).select_from(Complaint))).scalar_one())
        by_category = await self._group_count(Complaint.category)
        by_priority = await self._group_count(Complaint.priority)
        by_status = await self._group_count(Complaint.status)
        fallback_stmt = (
            select(func.count())
            .select_from(Complaint)
            .where(Complaint.triaged_by == "rules:fallback")
        )
        fallbacks = int((await self._session.execute(fallback_stmt)).scalar_one())
        return {
            "total": total,
            "by_category": {c.value: by_category.get(c.value, 0) for c in Category},
            "by_priority": {p.value: by_priority.get(p.value, 0) for p in Priority},
            "by_status": {s.value: by_status.get(s.value, 0) for s in Status},
            "fallback_rate": round(fallbacks / total, 4) if total else 0.0,
        }

    async def ping(self) -> bool:
        await self._session.execute(select(1))
        return True
