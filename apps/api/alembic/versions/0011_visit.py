"""visit — first-party page views for the admin's daily usage (docs/50)

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "visit",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True),
        sa.Column("visitor", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("path", sa.String(length=200), nullable=False),
        sa.Column("referrer", sa.String(length=120), nullable=True),
        sa.Column("device", sa.String(length=8), nullable=False, server_default="desktop"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_visit_created", "visit", ["created_at"])
    op.create_index("ix_visit_visitor", "visit", ["visitor"])


def downgrade() -> None:
    op.drop_index("ix_visit_visitor", table_name="visit")
    op.drop_index("ix_visit_created", table_name="visit")
    op.drop_table("visit")
