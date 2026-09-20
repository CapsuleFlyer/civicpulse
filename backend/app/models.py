"""SQLAlchemy ORM models.

Constraints are declared here *and* in the migration so the database rejects a
bad row even when the write does not come from this application (psql, a future
service, a botched data fix). The application's Pydantic validation is a fast,
friendly first line; the CHECK constraint is the one that actually holds.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Enum, Index, Integer, String, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.domain import Category, Priority, Status


class Base(DeclarativeBase):
    pass


class Complaint(Base):
    __tablename__ = "complaints"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    text: Mapped[str] = mapped_column(String(2000), nullable=False)
    location: Mapped[str] = mapped_column(String(200), nullable=False)
    reporter_contact: Mapped[str | None] = mapped_column(String(120), nullable=True)

    category: Mapped[Category] = mapped_column(
        Enum(Category, name="complaint_category", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    priority: Mapped[Priority] = mapped_column(
        Enum(Priority, name="complaint_priority", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    status: Mapped[Status] = mapped_column(
        Enum(Status, name="complaint_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=Status.OPEN,
    )

    ai_summary: Mapped[str | None] = mapped_column(String(140), nullable=True)
    triaged_by: Mapped[str] = mapped_column(String(32), nullable=False)
    triage_latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("length(text) >= 10 AND length(text) <= 2000", name="ck_complaints_text_len"),
        CheckConstraint(
            "length(location) >= 3 AND length(location) <= 200", name="ck_complaints_location_len"
        ),
        CheckConstraint("length(ai_summary) <= 140", name="ck_complaints_summary_len"),
        # Serves the dashboard's default query: the operator queue, filtered by
        # status and ordered so that high-priority work is on page one.
        Index("ix_complaints_status_priority", "status", "priority"),
        # Serves "newest first" on every list response and the stats window.
        Index("ix_complaints_created_at", "created_at"),
    )
