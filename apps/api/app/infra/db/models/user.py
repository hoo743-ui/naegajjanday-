from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.db.base import (
    Base,
    BigIntPK,
    JsonB,
    TimestampMixin,
    UtcDateTime,
    UuidStr,
    json_dict,
    json_list,
    new_uuid,
    pk,
)


class User(Base, TimestampMixin):
    __tablename__ = "user"

    id: Mapped[pk]
    public_id: Mapped[str] = mapped_column(UuidStr, unique=True, default=new_uuid)
    email: Mapped[str | None] = mapped_column(Text, unique=True)
    nickname: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(16), default="user")  # user | admin | operator
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | suspended | deleting
    delete_requested_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class OAuthAccount(Base, TimestampMixin):
    __tablename__ = "oauth_account"
    __table_args__ = (
        UniqueConstraint("provider", "provider_user_id", name="uq_oauth_account_provider_user"),
    )

    id: Mapped[pk]
    user_id: Mapped[int] = mapped_column(BigIntPK, ForeignKey("user.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(16))  # kakao | naver | google
    provider_user_id: Mapped[str] = mapped_column(Text)


class RefreshToken(Base, TimestampMixin):
    __tablename__ = "refresh_token"

    id: Mapped[pk]
    user_id: Mapped[int] = mapped_column(BigIntPK, ForeignKey("user.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    family_id: Mapped[str] = mapped_column(UuidStr, index=True)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class UserPreference(Base, TimestampMixin):
    __tablename__ = "user_preference"

    user_id: Mapped[int] = mapped_column(
        BigIntPK, ForeignKey("user.id", ondelete="CASCADE"), primary_key=True
    )
    liked_tags: Mapped[json_list]
    disliked_tags: Mapped[json_list]
    category_weights: Mapped[json_dict]
    # pgvector(64) is optional in the ERD; stored as JSON so SQLite and vanilla PostgreSQL both work.
    taste_vector: Mapped[list[float] | None] = mapped_column(JsonB)
    default_transport: Mapped[str] = mapped_column(String(16), default="walk")
