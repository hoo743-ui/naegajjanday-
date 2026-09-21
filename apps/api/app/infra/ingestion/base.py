"""Provider-agnostic ingestion contracts.

Every source (official Open API or file import) implements `PlaceProvider`:
`fetch()` yields raw payloads untouched, `normalize()` maps one payload to the canonical shape.
HTML scraping of Naver Place / Kakao Map / Google Maps is NOT allowed (ToS) — Open APIs only.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class RegionRef:
    """What a provider needs to know about the target region (comes from the `region` table)."""

    slug: str
    name: str
    center_lat: float
    center_lng: float
    radius_m: int
    area_code: str | None = None
    search_keywords: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RawPlace:
    provider: str
    external_id: str
    raw: dict[str, Any]
    kind: Literal["place", "event"] = "place"

    @property
    def content_hash(self) -> str:
        blob = json.dumps(self.raw, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class NormalizedMenu:
    name: str
    price: int
    is_signature: bool = False


@dataclass(slots=True)
class NormalizedHour:
    dow: int  # 0=Mon … 6=Sun
    open_time: str | None = None  # "HH:MM"
    close_time: str | None = None  # "HH:MM"; <= open_time means past midnight, "00:00"-"00:00" = 24h
    break_start: str | None = None
    break_end: str | None = None
    is_closed: bool = False


@dataclass(slots=True)
class NormalizedPlace:
    provider: str
    external_id: str
    name: str
    lat: float
    lng: float
    category_code: str | None = None  # canonical `category.code`; None → resolved via provider_mapping
    provider_categories: list[str] = field(default_factory=list)
    address: str | None = None
    road_address: str | None = None
    phone: str | None = None
    description: str | None = None
    thumbnail_url: str | None = None
    images: list[str] = field(default_factory=list)
    price_per_person: int | None = None
    is_free: bool = False
    menus: list[NormalizedMenu] = field(default_factory=list)
    opening_hours: list[NormalizedHour] = field(default_factory=list)
    popular_times: list[tuple[int, int, float]] = field(default_factory=list)  # (dow, hour, 0~1)
    rating_avg: float | None = None
    rating_count: int = 0
    sentiment_score: float | None = None  # aggregate only
    sentiment_count: int = 0
    aspect_scores: dict[str, float] = field(default_factory=dict)
    tags: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class NormalizedEvent:
    provider: str
    external_id: str
    title: str
    lat: float
    lng: float
    starts_on: date
    ends_on: date
    category_code: str | None = None
    provider_categories: list[str] = field(default_factory=list)
    description: str | None = None
    address: str | None = None
    price: int | None = None
    is_free: bool = False
    booking_url: str | None = None
    images: list[str] = field(default_factory=list)


class ProviderNotConfiguredError(RuntimeError):
    def __init__(self, provider: str, env_var: str) -> None:
        super().__init__(f"provider '{provider}' requires env {env_var}")
        self.provider = provider
        self.env_var = env_var


@runtime_checkable
class PlaceProvider(Protocol):
    name: str

    def fetch(self, region: RegionRef, cursor: dict[str, Any] | None = None) -> AsyncIterator[RawPlace]:
        """Yield raw payloads for the region. `cursor` lets an interrupted job resume."""
        ...

    def normalize(self, raw: RawPlace) -> NormalizedPlace | NormalizedEvent | None:
        """Pure mapping raw → canonical. Return None to skip unusable rows."""
        ...
