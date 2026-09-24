"""place_image credit columns (docs/43: photo sources, licences and attribution)

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-24

thumbnail_url / source_url / photographer / license / attribution_text: what the screen must show next
to a photo. Stored per photo because the licence differs per photo (TourAPI KOGL type 1 vs type 3).
All nullable; `cli images-credit --apply` fills the TourAPI rows from the raw cache.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMNS = ("thumbnail_url", "source_url", "photographer", "attribution_text")


def upgrade() -> None:
    for name in COLUMNS:
        op.add_column("place_image", sa.Column(name, sa.Text(), nullable=True))
    op.add_column("place_image", sa.Column("license", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("place_image", "license")
    for name in reversed(COLUMNS):
        op.drop_column("place_image", name)
