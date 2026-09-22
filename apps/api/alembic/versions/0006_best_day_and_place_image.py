"""course_stop.reason_codes + place_image (docs/29: Best Day engine, image pipeline)

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-22

reason_codes: why each place was chosen, as codes the UI can explain. Null for stops made before.
place_image: one row per photo of a place with its source, verification status and duplicate key.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.add_column("course_stop", sa.Column("reason_codes", JSON, nullable=True))
    op.create_table(
        "place_image",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("place_id", sa.BigInteger(), sa.ForeignKey("place.id", ondelete="CASCADE"), nullable=False),
        sa.Column("image_key", sa.String(length=64), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("source_place_id", sa.Text(), nullable=True),
        sa.Column("source_query", sa.Text(), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("image_type", sa.String(length=24), nullable=False),
        sa.Column("verification_status", sa.String(length=16), nullable=False),
        sa.Column("relevance", sa.Float(), nullable=False),
        sa.Column("file_hash", sa.String(length=64), nullable=True),
        sa.Column("phash", sa.String(length=16), nullable=True),
        sa.Column("evidence", JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("place_id", "image_key", name="uq_place_image_place_key"),
    )
    op.create_index("ix_place_image_place_id", "place_image", ["place_id"])
    op.create_index("ix_place_image_image_key", "place_image", ["image_key"])
    op.create_index("ix_place_image_verification_status", "place_image", ["verification_status"])


def downgrade() -> None:
    op.drop_index("ix_place_image_verification_status", table_name="place_image")
    op.drop_index("ix_place_image_image_key", table_name="place_image")
    op.drop_index("ix_place_image_place_id", table_name="place_image")
    op.drop_table("place_image")
    op.drop_column("course_stop", "reason_codes")
