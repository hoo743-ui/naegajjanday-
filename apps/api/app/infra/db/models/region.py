from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infra.db.base import Base, BigIntPK, TextArray, TimestampMixin, json_dict, pk

# NOTE: `geog geography(Point,4326)` generated columns + GIST indexes exist only on PostgreSQL and are
# created by the Alembic migration; the ORM never writes them.


class Region(Base, TimestampMixin):
    __tablename__ = "region"

    id: Mapped[pk]
    parent_id: Mapped[int | None] = mapped_column(BigIntPK, ForeignKey("region.id", ondelete="SET NULL"))
    slug: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    level: Mapped[int] = mapped_column(SmallInteger)  # 1=sido 2=sigungu 3=hotspot
    center_lat: Mapped[float]
    center_lng: Mapped[float]
    radius_m: Mapped[int] = mapped_column(Integer, default=1200)
    area_code: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    search_keywords: Mapped[list[str]] = mapped_column(TextArray, default=list)

    parent: Mapped[Region | None] = relationship(remote_side="Region.id", lazy="joined", join_depth=1)


class Category(Base, TimestampMixin):
    __tablename__ = "category"

    id: Mapped[pk]
    parent_id: Mapped[int | None] = mapped_column(BigIntPK, ForeignKey("category.id", ondelete="SET NULL"))
    code: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    course_role: Mapped[str] = mapped_column(String(16), index=True)
    default_stay_min: Mapped[int] = mapped_column(Integer, default=60)
    provider_mapping: Mapped[json_dict]


class Tag(Base, TimestampMixin):
    __tablename__ = "tag"

    id: Mapped[pk]
    name: Mapped[str] = mapped_column(Text, unique=True)
    group: Mapped[str] = mapped_column("group", String(32), default="feature", index=True)
    is_selectable: Mapped[bool] = mapped_column(default=True)


Index("ix_region_parent", Region.parent_id)
