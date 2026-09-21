from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import (
    CheckConstraint,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
    false,
)
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
from app.infra.db.models.region import Category, Region, Tag


class Place(Base, TimestampMixin):
    __tablename__ = "place"
    __table_args__ = (
        CheckConstraint("lat BETWEEN -90 AND 90", name="lat_range"),
        CheckConstraint("lng BETWEEN -180 AND 180", name="lng_range"),
        Index("ix_place_region_status_category", "region_id", "status", "category_id"),
        Index("ix_place_status_price", "status", "price_per_person"),
        Index("ix_place_lat_lng", "lat", "lng"),
        # candidate query: role (→ category ids) + status + bbox; keeps nationwide data index-only
        Index("ix_place_category_status_lat_lng", "category_id", "status", "lat", "lng"),
    )

    id: Mapped[pk]
    public_id: Mapped[str] = mapped_column(UuidStr, unique=True, default=new_uuid)
    region_id: Mapped[int] = mapped_column(BigIntPK, ForeignKey("region.id"))
    category_id: Mapped[int] = mapped_column(BigIntPK, ForeignKey("category.id"))
    name: Mapped[str] = mapped_column(Text)
    address: Mapped[str | None] = mapped_column(Text)
    road_address: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    lat: Mapped[float]
    lng: Mapped[float]
    price_per_person: Mapped[int | None] = mapped_column(Integer)
    price_tier: Mapped[int] = mapped_column(SmallInteger, default=1)
    # True = category-level prior (no menu data); False = measured from real menus / provider price
    price_is_estimated: Mapped[bool] = mapped_column(default=False, server_default=false())
    is_free: Mapped[bool] = mapped_column(default=False)
    description: Mapped[str | None] = mapped_column(Text)
    thumbnail_url: Mapped[str | None] = mapped_column(Text)
    images: Mapped[json_list]
    status: Mapped[str] = mapped_column(String(16), default="pending")
    data_quality: Mapped[float] = mapped_column(Float, default=0.0)
    last_verified_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    approved_at: Mapped[datetime | None] = mapped_column(UtcDateTime)

    region: Mapped[Region] = relationship(lazy="raise")
    category: Mapped[Category] = relationship(lazy="raise")
    stats: Mapped[PlaceStats | None] = relationship(back_populates="place", uselist=False, lazy="raise")
    menu_items: Mapped[list[MenuItem]] = relationship(lazy="raise", cascade="all, delete-orphan")
    opening_hours: Mapped[list[OpeningHour]] = relationship(lazy="raise", cascade="all, delete-orphan")
    popular_times: Mapped[list[PopularTime]] = relationship(lazy="raise", cascade="all, delete-orphan")
    place_tags: Mapped[list[PlaceTag]] = relationship(lazy="raise", cascade="all, delete-orphan")
    sources: Mapped[list[PlaceSource]] = relationship(lazy="raise")


class PlaceSource(Base, TimestampMixin):
    __tablename__ = "place_source"
    __table_args__ = (UniqueConstraint("provider", "external_id", name="uq_place_source_provider_external"),)

    id: Mapped[pk]
    place_id: Mapped[int | None] = mapped_column(
        BigIntPK, ForeignKey("place.id", ondelete="SET NULL"), index=True
    )
    provider: Mapped[str] = mapped_column(String(32))
    external_id: Mapped[str] = mapped_column(Text)
    raw: Mapped[json_dict]
    fetched_at: Mapped[datetime] = mapped_column(UtcDateTime)
    content_hash: Mapped[str] = mapped_column(String(64))
    match_confidence: Mapped[float | None] = mapped_column(Float)


class PlaceStats(Base, TimestampMixin):
    __tablename__ = "place_stats"

    place_id: Mapped[int] = mapped_column(
        BigIntPK, ForeignKey("place.id", ondelete="CASCADE"), primary_key=True
    )
    rating_avg: Mapped[float | None] = mapped_column(Float)
    rating_count: Mapped[int] = mapped_column(Integer, default=0)
    bayes_rating: Mapped[float | None] = mapped_column(Float)
    sentiment_score: Mapped[float | None] = mapped_column(Float)
    sentiment_count: Mapped[int] = mapped_column(Integer, default=0)
    aspect_scores: Mapped[json_dict]
    popularity: Mapped[float] = mapped_column(Float, default=0.0)
    recommend_count: Mapped[int] = mapped_column(Integer, default=0)
    save_count: Mapped[int] = mapped_column(Integer, default=0)
    visit_feedback_avg: Mapped[float | None] = mapped_column(Float)

    place: Mapped[Place] = relationship(back_populates="stats", lazy="raise")


class MenuItem(Base, TimestampMixin):
    __tablename__ = "menu_item"

    id: Mapped[pk]
    place_id: Mapped[int] = mapped_column(BigIntPK, ForeignKey("place.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(Text)
    price: Mapped[int] = mapped_column(Integer)
    is_signature: Mapped[bool] = mapped_column(default=False)
    source: Mapped[str] = mapped_column(String(32), default="file")


class OpeningHour(Base, TimestampMixin):
    __tablename__ = "opening_hour"
    __table_args__ = (
        UniqueConstraint("place_id", "dow", name="uq_opening_hour_place_dow"),
        CheckConstraint("dow BETWEEN 0 AND 6", name="dow_range"),
    )

    id: Mapped[pk]
    place_id: Mapped[int] = mapped_column(BigIntPK, ForeignKey("place.id", ondelete="CASCADE"), index=True)
    dow: Mapped[int] = mapped_column(SmallInteger)  # 0=Mon .. 6=Sun
    open_time: Mapped[time | None] = mapped_column(Time)
    close_time: Mapped[time | None] = mapped_column(Time)  # <= open_time means past midnight
    break_start: Mapped[time | None] = mapped_column(Time)
    break_end: Mapped[time | None] = mapped_column(Time)
    is_closed: Mapped[bool] = mapped_column(default=False)


class PopularTime(Base):
    __tablename__ = "popular_time"

    place_id: Mapped[int] = mapped_column(
        BigIntPK, ForeignKey("place.id", ondelete="CASCADE"), primary_key=True
    )
    dow: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    hour: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    congestion: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(32), default="file")


class Review(Base, TimestampMixin):
    """Body text is stored only for providers whose terms allow it; else aggregates go to place_stats."""

    __tablename__ = "review"
    __table_args__ = (UniqueConstraint("provider", "external_id", name="uq_review_provider_external"),)

    id: Mapped[pk]
    place_id: Mapped[int] = mapped_column(BigIntPK, ForeignKey("place.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(32))
    external_id: Mapped[str] = mapped_column(Text)
    rating: Mapped[float | None] = mapped_column(Float)
    content: Mapped[str | None] = mapped_column(Text)
    written_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    sentiment: Mapped[float | None] = mapped_column(Float)
    aspects: Mapped[json_dict]
    analyzed_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    model_version: Mapped[str | None] = mapped_column(String(64))


class PlaceTag(Base):
    __tablename__ = "place_tag"

    place_id: Mapped[int] = mapped_column(
        BigIntPK, ForeignKey("place.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(BigIntPK, ForeignKey("tag.id", ondelete="CASCADE"), primary_key=True)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    source: Mapped[str] = mapped_column(String(16), default="file")  # llm | admin | file | provider

    tag: Mapped[Tag] = relationship(lazy="joined")


class Event(Base, TimestampMixin):
    __tablename__ = "event"
    __table_args__ = (
        UniqueConstraint("provider", "external_id", name="uq_event_provider_external"),
        Index("ix_event_region_period", "region_id", "starts_on", "ends_on"),
    )

    id: Mapped[pk]
    public_id: Mapped[str] = mapped_column(UuidStr, unique=True, default=new_uuid)
    region_id: Mapped[int] = mapped_column(BigIntPK, ForeignKey("region.id"))
    place_id: Mapped[int | None] = mapped_column(BigIntPK, ForeignKey("place.id", ondelete="SET NULL"))
    category_id: Mapped[int | None] = mapped_column(BigIntPK, ForeignKey("category.id"))
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    address: Mapped[str | None] = mapped_column(Text)
    lat: Mapped[float]
    lng: Mapped[float]
    starts_on: Mapped[date] = mapped_column(Date)
    ends_on: Mapped[date] = mapped_column(Date)
    price: Mapped[int | None] = mapped_column(Integer)
    is_free: Mapped[bool] = mapped_column(default=False)
    booking_url: Mapped[str | None] = mapped_column(Text)
    images: Mapped[json_list]
    provider: Mapped[str] = mapped_column(String(32), default="admin")
    external_id: Mapped[str] = mapped_column(Text, default=new_uuid)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)

    category: Mapped[Category | None] = relationship(lazy="raise")
