"""api_usage — calls per external API per day, for quota alerts (docs/47)

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "api_usage",
        sa.Column("provider", sa.String(length=32), primary_key=True),
        sa.Column("day", sa.String(length=8), primary_key=True),
        sa.Column("calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("errors", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("exhausted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("remaining", sa.Integer(), nullable=True),
        sa.Column("limit", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("api_usage")
