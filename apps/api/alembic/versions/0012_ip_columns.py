"""visit.ip · recommendation_log.ip — who sent it, kept 90 days for spotting abuse (docs/50)

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("visit", sa.Column("ip", sa.String(length=45), nullable=True))
    op.add_column("recommendation_log", sa.Column("ip", sa.String(length=45), nullable=True))


def downgrade() -> None:
    op.drop_column("recommendation_log", "ip")
    op.drop_column("visit", "ip")
