from __future__ import annotations

from datetime import time

from sqlalchemy import Float, ForeignKey, Integer, SmallInteger, String, Text, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infra.db.base import Base, BigIntPK, TimestampMixin, json_dict, pk
from app.infra.db.models.region import Tag


class Purpose(Base, TimestampMixin):
    __tablename__ = "purpose"

    id: Mapped[pk]
    code: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    icon: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    budget_min: Mapped[int | None] = mapped_column(Integer)  # recommended total budget range (UI hint)
    budget_max: Mapped[int | None] = mapped_column(Integer)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(default=True)


class CourseTemplate(Base, TimestampMixin):
    __tablename__ = "course_template"

    id: Mapped[pk]
    purpose_id: Mapped[int] = mapped_column(
        BigIntPK, ForeignKey("purpose.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    time_band: Mapped[str] = mapped_column(String(16))  # lunch | afternoon | evening | fullday
    min_budget_per_person: Mapped[int] = mapped_column(Integer, default=0)
    party_min: Mapped[int] = mapped_column(SmallInteger, default=1)
    party_max: Mapped[int] = mapped_column(SmallInteger, default=8)
    is_active: Mapped[bool] = mapped_column(default=True)

    slots: Mapped[list[TemplateSlot]] = relationship(
        order_by="TemplateSlot.position", cascade="all, delete-orphan", lazy="selectin"
    )


class TemplateSlot(Base, TimestampMixin):
    __tablename__ = "template_slot"
    __table_args__ = (UniqueConstraint("template_id", "position", name="uq_template_slot_position"),)

    id: Mapped[pk]
    template_id: Mapped[int] = mapped_column(BigIntPK, ForeignKey("course_template.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(SmallInteger)
    course_role: Mapped[str] = mapped_column(String(16))
    budget_share: Mapped[float] = mapped_column(Float)
    is_optional: Mapped[bool] = mapped_column(default=False)
    is_order_flexible: Mapped[bool] = mapped_column(default=False)
    earliest_start: Mapped[time | None] = mapped_column(Time)
    latest_start: Mapped[time | None] = mapped_column(Time)
    min_slot_budget: Mapped[int | None] = mapped_column(Integer)  # optional slot is dropped below this b_s


class ScoringProfile(Base, TimestampMixin):
    __tablename__ = "scoring_profile"

    id: Mapped[pk]
    purpose_id: Mapped[int] = mapped_column(
        BigIntPK, ForeignKey("purpose.id", ondelete="CASCADE"), unique=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    weights: Mapped[json_dict]
    params: Mapped[json_dict]
    is_active: Mapped[bool] = mapped_column(default=True)
    experiment_key: Mapped[str | None] = mapped_column(Text)


class PurposeTagAffinity(Base):
    __tablename__ = "purpose_tag_affinity"

    purpose_id: Mapped[int] = mapped_column(
        BigIntPK, ForeignKey("purpose.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(BigIntPK, ForeignKey("tag.id", ondelete="CASCADE"), primary_key=True)
    weight: Mapped[float] = mapped_column(Float)  # -1 .. 1

    tag: Mapped[Tag] = relationship(lazy="joined")
