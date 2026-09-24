from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.db.base import (
    Base,
    BigIntPK,
    JsonB,
    TimestampMixin,
    UtcDateTime,
    json_dict,
    json_list,
    pk,
    utcnow,
)


class Banner(Base, TimestampMixin):
    __tablename__ = "banner"

    id: Mapped[pk]
    title: Mapped[str] = mapped_column(Text)
    image_url: Mapped[str] = mapped_column(Text)
    link_url: Mapped[str | None] = mapped_column(Text)
    placement: Mapped[str] = mapped_column(String(32), default="home", index=True)
    region_id: Mapped[int | None] = mapped_column(BigIntPK, ForeignKey("region.id", ondelete="SET NULL"))
    starts_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    ends_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(default=True)


class IngestionJob(Base, TimestampMixin):
    __tablename__ = "ingestion_job"

    id: Mapped[pk]
    provider: Mapped[str] = mapped_column(String(32))
    region_id: Mapped[int | None] = mapped_column(
        BigIntPK, ForeignKey("region.id", ondelete="SET NULL"), index=True
    )
    job_type: Mapped[str] = mapped_column(String(16), default="full")  # full|incremental|stats|sentiment
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    cursor: Mapped[dict[str, Any] | None] = mapped_column(JsonB)
    params: Mapped[json_dict]
    fetched_count: Mapped[int] = mapped_column(Integer, default=0)
    created_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class PlaceRevision(Base, TimestampMixin):
    __tablename__ = "place_revision"

    id: Mapped[pk]
    place_id: Mapped[int] = mapped_column(BigIntPK, ForeignKey("place.id", ondelete="CASCADE"), index=True)
    admin_id: Mapped[int | None] = mapped_column(BigIntPK, ForeignKey("user.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(16))  # approve | reject | edit | merge | create
    before: Mapped[dict[str, Any] | None] = mapped_column(JsonB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JsonB)
    note: Mapped[str | None] = mapped_column(Text)


class AuditLog(Base, TimestampMixin):
    """Every admin write. Monthly partitioning is an ops step on PostgreSQL."""

    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_entity", "entity", "entity_id"),)

    id: Mapped[pk]
    actor_id: Mapped[int | None] = mapped_column(
        BigIntPK, ForeignKey("user.id", ondelete="SET NULL"), index=True
    )
    action: Mapped[str] = mapped_column(String(64))
    entity: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str | None] = mapped_column(Text)
    diff: Mapped[json_dict]
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(Text)


class ApiKey(Base, TimestampMixin):
    __tablename__ = "api_key"

    id: Mapped[pk]
    name: Mapped[str] = mapped_column(Text)
    key_hash: Mapped[str] = mapped_column("hash", String(64), unique=True)
    scopes: Mapped[json_list]
    rate_limit: Mapped[int] = mapped_column(Integer, default=60)
    revoked_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class SearchOutbox(Base, TimestampMixin):
    """Transactional outbox: the SQL database is canonical, a worker drains this into Elasticsearch."""

    __tablename__ = "search_outbox"

    id: Mapped[pk]
    entity: Mapped[str] = mapped_column(String(16), default="place")
    entity_id: Mapped[int] = mapped_column(BigIntPK)
    op: Mapped[str] = mapped_column(String(8), default="upsert")  # upsert | delete
    processed_at: Mapped[datetime | None] = mapped_column(UtcDateTime, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)


class ApiUsage(Base):
    """Calls to one external API on one day (docs/47) — counted by the httpx hook in infra/api_usage.py.
    `exhausted_at` is set when the provider said the quota is used up (HTTP 429 or data.go.kr code 22)."""

    __tablename__ = "api_usage"

    provider: Mapped[str] = mapped_column(String(32), primary_key=True)
    day: Mapped[str] = mapped_column(String(8), primary_key=True)  # YYYYMMDD, Asia/Seoul
    calls: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[int] = mapped_column(Integer, default=0)
    exhausted_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    remaining: Mapped[int | None] = mapped_column(Integer)  # from the provider's rate-limit header, when sent
    limit: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class Visit(Base):
    """One page view, first-party (docs/50): who came — logged in or not — without an analytics vendor.
    `visitor` is a keyed hash of a random id the browser keeps; no IP, no user agent string is stored."""

    __tablename__ = "visit"
    __table_args__ = (Index("ix_visit_created", "created_at"),)

    id: Mapped[pk]
    visitor: Mapped[str] = mapped_column(String(32), index=True)
    user_id: Mapped[int | None] = mapped_column(BigIntPK, ForeignKey("user.id", ondelete="SET NULL"))
    path: Mapped[str] = mapped_column(String(200))
    referrer: Mapped[str | None] = mapped_column(String(120))  # host only: "instagram.com", "kakao"
    device: Mapped[str] = mapped_column(String(8), default="desktop")  # mobile | tablet | desktop
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
