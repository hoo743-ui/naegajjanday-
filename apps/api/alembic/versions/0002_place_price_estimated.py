"""place.price_is_estimated + candidate-query index for nationwide bulk data

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-21

Public bulk files carry no menu prices, so most places get a category-level price prior. The flag lets
the API/UI tell an estimate ("예상") from a measured price. The index keeps the role + bbox candidate
query index-only once `place` holds ~1M rows.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("place", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("price_is_estimated", sa.Boolean(), server_default=sa.false(), nullable=False)
        )
        batch_op.create_index(
            "ix_place_category_status_lat_lng", ["category_id", "status", "lat", "lng"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("place", schema=None) as batch_op:
        batch_op.drop_index("ix_place_category_status_lat_lng")
        batch_op.drop_column("price_is_estimated")
