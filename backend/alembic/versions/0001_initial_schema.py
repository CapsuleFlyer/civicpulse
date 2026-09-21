"""initial complaints schema

Revision ID: 0001
Revises:
Create Date: 2026-09-01

Reversible on purpose: downgrade() drops the table *and* the three enum types,
because a half-dropped PostgreSQL enum makes the next upgrade fail with a
confusing "type already exists".
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels = None
depends_on = None

CATEGORY = sa.Enum(
    "water", "electricity", "sanitation", "roads", "streetlights", "other",
    name="complaint_category",
)
PRIORITY = sa.Enum("high", "normal", "low", name="complaint_priority")
STATUS = sa.Enum("open", "in_progress", "resolved", "rejected", name="complaint_status")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # gen_random_uuid() lives in pgcrypto on older servers; on 13+ it is core.
        op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    server_default_uuid = sa.text("gen_random_uuid()") if bind.dialect.name == "postgresql" else None

    op.create_table(
        "complaints",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=server_default_uuid),
        sa.Column("text", sa.String(length=2000), nullable=False),
        sa.Column("location", sa.String(length=200), nullable=False),
        sa.Column("reporter_contact", sa.String(length=120), nullable=True),
        sa.Column("category", CATEGORY, nullable=False),
        sa.Column("priority", PRIORITY, nullable=False),
        sa.Column("status", STATUS, nullable=False, server_default="open"),
        sa.Column("ai_summary", sa.String(length=140), nullable=True),
        sa.Column("triaged_by", sa.String(length=32), nullable=False),
        sa.Column("triage_latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("length(text) >= 10 AND length(text) <= 2000", name="ck_complaints_text_len"),
        sa.CheckConstraint("length(location) >= 3 AND length(location) <= 200", name="ck_complaints_location_len"),
        sa.CheckConstraint("length(ai_summary) <= 140", name="ck_complaints_summary_len"),
    )
    # Serves the dashboard queue query: WHERE status = ? AND priority = ?
    op.create_index("ix_complaints_status_priority", "complaints", ["status", "priority"])
    # Serves ORDER BY created_at DESC on every list page and the stats window.
    op.create_index("ix_complaints_created_at", "complaints", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_complaints_created_at", table_name="complaints")
    op.drop_index("ix_complaints_status_priority", table_name="complaints")
    op.drop_table("complaints")
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for enum in (STATUS, PRIORITY, CATEGORY):
            enum.drop(bind, checkfirst=True)
