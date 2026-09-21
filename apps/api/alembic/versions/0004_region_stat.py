"""region_stat: place counts of regions that own no places (동 · 읍 · 면, level 4)

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-22

Filled by `python -m app.infra.ingestion.bulk.dongs`. Derived data only.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "region_stat",
        sa.Column(
            "region_id", sa.BigInteger(), sa.ForeignKey("region.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("place_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("region_stat")
