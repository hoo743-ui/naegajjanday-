from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from sqlalchemy import JSON, BigInteger, DateTime, Integer, MetaData, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

# Portable column types: PostgreSQL gets the real thing, SQLite (local/tests) a compatible variant.
BigIntPK = BigInteger().with_variant(Integer, "sqlite")
JsonB = JSON().with_variant(JSONB(), "postgresql")
TextArray = JSON().with_variant(ARRAY(Text), "postgresql")
UuidStr = String(36).with_variant(PG_UUID(as_uuid=False), "postgresql")


class UtcDateTime(TypeDecorator[datetime]):
    """timestamptz everywhere: values are normalized to UTC on write and come back tz-aware.

    SQLite has no timezone support and would silently drop the offset of a +09:00 value.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime is not allowed; attach a timezone")
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

pk = Annotated[int, mapped_column(BigIntPK, primary_key=True, autoincrement=True)]
json_dict = Annotated[dict[str, Any], mapped_column(JsonB, default=dict)]
json_list = Annotated[list[Any], mapped_column(JsonB, default=list)]


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime, default=utcnow, onupdate=utcnow, server_default=func.now()
    )


def as_utc(dt: datetime | None) -> datetime | None:
    """SQLite drops tzinfo; everything is stored as UTC."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
