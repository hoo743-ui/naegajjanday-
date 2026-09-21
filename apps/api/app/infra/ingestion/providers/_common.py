"""Shared helpers for Open-API providers (HTTP client lifecycle, geo math, parsing)."""

from __future__ import annotations

import math
import re
from typing import Any

import httpx

DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
PAGE_DELAY_S = 0.15  # politeness delay between pages

_TAG_RE = re.compile(r"<[^>]+>")


class HttpClientMixin:
    """Owns an `httpx.AsyncClient` unless one is injected (tests / shared pool)."""

    _client: httpx.AsyncClient | None
    _owns_client: bool

    def _init_client(self, client: httpx.AsyncClient | None) -> None:
        self._client = client
        self._owns_client = client is None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=DEFAULT_TIMEOUT)
        return self._client

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def strip_html(text: str | None) -> str:
    return _TAG_RE.sub("", text or "").strip()


def to_float(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def valid_coord(lat: float | None, lng: float | None) -> bool:
    return (
        lat is not None
        and lng is not None
        and -90 <= lat <= 90
        and -180 <= lng <= 180
        and (lat, lng) != (0, 0)
    )


def clean(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None
