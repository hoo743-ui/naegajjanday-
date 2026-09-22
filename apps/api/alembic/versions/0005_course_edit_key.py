"""course.edit_key_hash: only the anonymous creator may edit an ownerless course (docs/28, release audit P0)

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-22

Nullable: courses generated before this revision keep their old (open) behaviour.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("course", sa.Column("edit_key_hash", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("course", "edit_key_hash")
