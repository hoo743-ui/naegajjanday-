"""event.anchor_place_id / start_time / end_time / priority (docs/34: a festival anchored to a campus)

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-23

anchor_place_id: the campus (a place in `attraction.campus`) whose festival this is — the universityId.
start_time / end_time: "HH:MM" of the day it runs, so the engine can check that it fits the day.
priority: the core slot of a festival day goes to the highest one when a campus has several.
All nullable / defaulted: events loaded before keep their date-only behaviour.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "event",
        sa.Column(
            "anchor_place_id", sa.BigInteger(), sa.ForeignKey("place.id", ondelete="SET NULL"), nullable=True
        ),
    )
    op.create_index("ix_event_anchor_place_id", "event", ["anchor_place_id"])
    op.add_column("event", sa.Column("start_time", sa.String(length=5), nullable=True))
    op.add_column("event", sa.Column("end_time", sa.String(length=5), nullable=True))
    op.add_column("event", sa.Column("priority", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("event", "priority")
    op.drop_column("event", "end_time")
    op.drop_column("event", "start_time")
    op.drop_index("ix_event_anchor_place_id", table_name="event")
    op.drop_column("event", "anchor_place_id")
