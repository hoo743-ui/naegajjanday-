"""region_signature: what each neighbourhood is known for (derived from place names)

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-21

Filled by `python -m app.cli build-signatures`. Derived data only: dropping the table loses nothing
that a rebuild does not bring back.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "region_signature",
        sa.Column("region_id", sa.BigInteger(), sa.ForeignKey("region.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("payload", postgresql.JSONB().with_variant(sa.JSON(), "sqlite"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("region_signature")
