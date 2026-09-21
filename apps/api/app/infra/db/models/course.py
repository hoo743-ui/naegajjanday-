from __future__ import annotations

from datetime import datetime

from sqlalchemy import Float, ForeignKey, Index, Integer, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infra.db.base import (
    Base,
    BigIntPK,
    TimestampMixin,
    UtcDateTime,
    UuidStr,
    json_dict,
    json_list,
    new_uuid,
    pk,
)
from app.infra.db.models.place import Event, Place


class RecommendationLog(Base, TimestampMixin):
    """Single source of truth for stats / A-B / replay. Monthly partitioning is an ops step on PostgreSQL."""

    __tablename__ = "recommendation_log"
    __table_args__ = (Index("ix_recommendation_log_created", "created_at"),)

    id: Mapped[pk]
    request_id: Mapped[str] = mapped_column(String(36), index=True)
    user_id: Mapped[int | None] = mapped_column(BigIntPK, ForeignKey("user.id", ondelete="SET NULL"))
    region_id: Mapped[int | None] = mapped_column(BigIntPK, ForeignKey("region.id"))
    purpose_id: Mapped[int | None] = mapped_column(BigIntPK, ForeignKey("purpose.id"))
    request: Mapped[json_dict]
    candidate_count: Mapped[int] = mapped_column(Integer, default=0)
    scoring_profile_version: Mapped[str | None] = mapped_column(String(64))
    engine_version: Mapped[str] = mapped_column(String(16))
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    selected_courses: Mapped[json_list]
    warnings: Mapped[json_list]


class Course(Base, TimestampMixin):
    __tablename__ = "course"

    id: Mapped[pk]
    public_id: Mapped[str] = mapped_column(UuidStr, unique=True, default=new_uuid)
    user_id: Mapped[int | None] = mapped_column(
        BigIntPK, ForeignKey("user.id", ondelete="SET NULL"), index=True
    )
    region_id: Mapped[int | None] = mapped_column(BigIntPK, ForeignKey("region.id"))
    purpose_id: Mapped[int] = mapped_column(BigIntPK, ForeignKey("purpose.id"))
    template_id: Mapped[int | None] = mapped_column(
        BigIntPK, ForeignKey("course_template.id", ondelete="SET NULL")
    )
    party_size: Mapped[int] = mapped_column(SmallInteger)
    budget_total: Mapped[int] = mapped_column(Integer)
    transport: Mapped[str] = mapped_column(String(16), default="walk")
    origin_lat: Mapped[float]
    origin_lng: Mapped[float]
    start_at: Mapped[datetime] = mapped_column(UtcDateTime)
    label: Mapped[str] = mapped_column(Text, default="추천 코스")
    total_price: Mapped[int] = mapped_column(Integer, default=0)
    total_travel_min: Mapped[int] = mapped_column(Integer, default=0)
    total_distance_m: Mapped[int] = mapped_column(Integer, default=0)
    total_score: Mapped[float] = mapped_column(Float, default=0.0)
    duration_min: Mapped[int] = mapped_column(Integer, default=0)
    optimizer: Mapped[str | None] = mapped_column(String(16))
    summary: Mapped[str | None] = mapped_column(Text)
    narrative: Mapped[str | None] = mapped_column(Text)
    tip: Mapped[str | None] = mapped_column(Text)
    warnings: Mapped[json_list]
    request: Mapped[json_dict]  # preferences etc. needed to re-plan on swap / reorder
    status: Mapped[str] = mapped_column(String(16), default="generated", index=True)
    recommendation_log_id: Mapped[int | None] = mapped_column(
        BigIntPK, ForeignKey("recommendation_log.id", ondelete="SET NULL")
    )

    stops: Mapped[list[CourseStop]] = relationship(
        order_by="CourseStop.position", cascade="all, delete-orphan", lazy="selectin"
    )


class CourseStop(Base, TimestampMixin):
    __tablename__ = "course_stop"
    __table_args__ = (Index("ix_course_stop_course_position", "course_id", "position"),)

    id: Mapped[pk]
    course_id: Mapped[int] = mapped_column(BigIntPK, ForeignKey("course.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(SmallInteger)
    place_id: Mapped[int | None] = mapped_column(BigIntPK, ForeignKey("place.id", ondelete="SET NULL"))
    event_id: Mapped[int | None] = mapped_column(BigIntPK, ForeignKey("event.id", ondelete="SET NULL"))
    course_role: Mapped[str] = mapped_column(String(16))
    arrive_at: Mapped[datetime] = mapped_column(UtcDateTime)
    leave_at: Mapped[datetime] = mapped_column(UtcDateTime)
    est_price: Mapped[int] = mapped_column(Integer, default=0)
    travel_min_from_prev: Mapped[int] = mapped_column(Integer, default=0)
    distance_m_from_prev: Mapped[int] = mapped_column(Integer, default=0)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    score_breakdown: Mapped[json_dict]
    reason: Mapped[str | None] = mapped_column(Text)
    congestion: Mapped[float | None] = mapped_column(Float)
    slot: Mapped[json_dict]  # snapshot of the template slot + allocated budget (for swap / reorder)

    place: Mapped[Place | None] = relationship(lazy="raise")
    event: Mapped[Event | None] = relationship(lazy="raise")


class CourseFeedback(Base, TimestampMixin):
    __tablename__ = "course_feedback"

    id: Mapped[pk]
    course_id: Mapped[int] = mapped_column(BigIntPK, ForeignKey("course.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(BigIntPK, ForeignKey("user.id", ondelete="CASCADE"), index=True)
    rating: Mapped[int] = mapped_column(SmallInteger)
    visited: Mapped[bool] = mapped_column(default=False)
    actual_spend: Mapped[int | None] = mapped_column(Integer)
    comment: Mapped[str | None] = mapped_column(Text)
    stop_feedback: Mapped[json_list]


class ChatSession(Base, TimestampMixin):
    __tablename__ = "chat_session"

    id: Mapped[pk]
    public_id: Mapped[str] = mapped_column(UuidStr, unique=True, default=new_uuid)
    user_id: Mapped[int | None] = mapped_column(
        BigIntPK, ForeignKey("user.id", ondelete="SET NULL"), index=True
    )
    context: Mapped[json_dict]


class ChatMessage(Base, TimestampMixin):
    __tablename__ = "chat_message"

    id: Mapped[pk]
    session_id: Mapped[int] = mapped_column(
        BigIntPK, ForeignKey("chat_session.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text, default="")
    tool_calls: Mapped[json_list]
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    model: Mapped[str | None] = mapped_column(String(64))
