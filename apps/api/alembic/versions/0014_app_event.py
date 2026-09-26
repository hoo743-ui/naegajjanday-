"""app_event — first-party product events from the web's track() (docs/62)

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_event",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True),
        sa.Column("name", sa.String(length=48), nullable=False),
        sa.Column("device", sa.String(length=32), nullable=False),
        sa.Column(
            "user_id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("course_id", sa.String(length=36), nullable=True),
        sa.Column("path", sa.String(length=200), nullable=True),
        sa.Column(
            "props",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_app_event_created", "app_event", ["created_at"])
    op.create_index("ix_app_event_name_created", "app_event", ["name", "created_at"])
    op.create_index("ix_app_event_device", "app_event", ["device"])
    op.create_index("ix_app_event_course_id", "app_event", ["course_id"])


def downgrade() -> None:
    op.drop_index("ix_app_event_course_id", table_name="app_event")
    op.drop_index("ix_app_event_device", table_name="app_event")
    op.drop_index("ix_app_event_name_created", table_name="app_event")
    op.drop_index("ix_app_event_created", table_name="app_event")
    op.drop_table("app_event")
