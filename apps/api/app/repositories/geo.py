"""Portable geo filter: bbox prefilter on lat/lng everywhere, ST_DWithin on `geog` for PostgreSQL."""

from __future__ import annotations

import math
from typing import Any

from sqlalchemy import ColumnElement, and_, func, literal_column

from app.domain.models import GeoPoint

METERS_PER_DEG_LAT = 111_320.0


def bbox(origin: GeoPoint, radius_m: float) -> tuple[float, float, float, float]:
    dlat = radius_m / METERS_PER_DEG_LAT
    dlng = radius_m / (METERS_PER_DEG_LAT * max(0.01, math.cos(math.radians(origin.lat))))
    return origin.lat - dlat, origin.lat + dlat, origin.lng - dlng, origin.lng + dlng


def nearest_first(model: Any, origin: GeoPoint) -> ColumnElement[float]:
    """ORDER BY key: squared equirectangular distance — portable SQL, exact enough to rank a bbox.

    Without it `LIMIT n` keeps whatever the index scan meets first (the bbox's southern edge), which
    matters as soon as a region holds more candidates than the limit (nationwide data).
    """
    k = math.cos(math.radians(origin.lat))
    dlat = model.lat - origin.lat
    dlng = (model.lng - origin.lng) * k
    expr: ColumnElement[float] = dlat * dlat + dlng * dlng
    return expr


def within(model: Any, origin: GeoPoint, radius_m: float, dialect: str) -> ColumnElement[bool]:
    lat_lo, lat_hi, lng_lo, lng_hi = bbox(origin, radius_m)
    box = and_(model.lat.between(lat_lo, lat_hi), model.lng.between(lng_lo, lng_hi))
    if dialect != "postgresql":
        return box  # exact haversine is applied in Python afterwards
    # generated column, PostgreSQL only
    geog: ColumnElement[Any] = literal_column(f"{model.__tablename__}.geog")
    point = func.ST_GeogFromText(f"SRID=4326;POINT({origin.lng:.7f} {origin.lat:.7f})")
    return and_(box, func.ST_DWithin(geog, point, radius_m))
