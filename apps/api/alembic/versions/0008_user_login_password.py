"""user.login_id / password_hash — self-managed id/password accounts (no e-mail verification)

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-23

login_id: stored trimmed + lowercase, unique through the index `ix_user_login_id` (an index rather than a
UNIQUE column constraint, so the same DDL also works as a plain ADD COLUMN on an existing SQLite file).
password_hash: `scrypt$n$r$p$salt_b64$hash_b64` (app.core.security.hash_password).
Both nullable: OAuth-only accounts keep them NULL.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("user", sa.Column("login_id", sa.Text(), nullable=True))
    op.add_column("user", sa.Column("password_hash", sa.Text(), nullable=True))
    op.create_index("ix_user_login_id", "user", ["login_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_user_login_id", table_name="user")
    with op.batch_alter_table("user") as batch:  # SQLite < 3.35 has no DROP COLUMN
        batch.drop_column("password_hash")
        batch.drop_column("login_id")
