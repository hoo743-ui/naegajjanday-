"""공연예술통합전산망(KOPIS) Open API client: performance list → detail → venue.

Official open API (key issued on application); responses are XML. Settings live in
`data/performances/kopis.json`, the key in `KOPIS_API_KEY`. With an empty key every method returns an
empty result and NO request is made. Nothing happens at import time.

XML is parsed with the standard library (`defusedxml` is not a dependency). `xml.etree` does not
resolve external entities, but it is not hardened against entity-expansion bombs — so it is used ONLY
on responses from this one trusted official host, never on user-supplied documents.

Responses are cached in-process with a TTL: one page view must not become dozens of upstream calls.
The key travels as a query parameter, so request URLs and exception messages are never logged.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time as _time
import xml.etree.ElementTree as ET  # trusted official host only — see the module docstring
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import httpx

from app.core.config import API_ROOT

log = logging.getLogger(__name__)
RULES_PATH = API_ROOT / "data" / "performances" / "kopis.json"
_MISSING = object()


@dataclass(frozen=True, slots=True)
class PerformanceSummary:
    id: str
    title: str
    date_from: date | None
    date_to: date | None
    venue_name: str
    poster_url: str | None = None
    area: str | None = None
    genre: str | None = None
    state: str | None = None


@dataclass(frozen=True, slots=True)
class PerformanceDetail:
    id: str
    title: str
    date_from: date | None
    date_to: date | None
    venue_name: str
    venue_id: str | None
    runtime_text: str | None = None
    price_text: str | None = None
    showtimes_text: str | None = None
    poster_url: str | None = None
    genre: str | None = None
    state: str | None = None


@dataclass(frozen=True, slots=True)
class Venue:
    id: str
    name: str
    address: str | None
    lat: float | None
    lng: float | None


@dataclass(frozen=True, slots=True)
class KopisRules:
    base_url: str = "https://www.kopis.or.kr/openApi/restful"
    detail_url_template: str = ""
    attribution: str = ""
    timeout_s: float = 10.0
    rows: int = 100
    max_list_pages: int = 3
    max_upstream_calls_per_request: int = 40
    max_seconds_per_request: float = 7.0
    concurrency: int = 5
    ttl_list_s: float = 1800.0
    ttl_detail_s: float = 21600.0
    ttl_venue_s: float = 86400.0
    area_codes_by_sido_slug: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    @classmethod
    def from_data(cls, data: Mapping[str, Any]) -> KopisRules:
        ttl = data.get("ttl_s", {})
        base = cls()
        return cls(
            base_url=str(data.get("base_url", base.base_url)).rstrip("/"),
            detail_url_template=str(data.get("detail_url_template", "")),
            attribution=str(data.get("attribution", "")),
            timeout_s=float(data.get("timeout_s", base.timeout_s)),
            rows=int(data.get("rows", base.rows)),
            max_list_pages=int(data.get("max_list_pages", base.max_list_pages)),
            max_upstream_calls_per_request=int(
                data.get("max_upstream_calls_per_request", base.max_upstream_calls_per_request)
            ),
            concurrency=max(1, int(data.get("concurrency", base.concurrency))),
            max_seconds_per_request=float(data.get("max_seconds_per_request", base.max_seconds_per_request)),
            ttl_list_s=float(ttl.get("list", base.ttl_list_s)),
            ttl_detail_s=float(ttl.get("detail", base.ttl_detail_s)),
            ttl_venue_s=float(ttl.get("venue", base.ttl_venue_s)),
            area_codes_by_sido_slug={
                str(slug): tuple(str(c) for c in codes)
                for slug, codes in data.get("area_codes_by_sido_slug", {}).items()
            },
        )

    def detail_url(self, performance_id: str) -> str | None:
        return self.detail_url_template.format(id=performance_id) if self.detail_url_template else None


def load_rules(path: Path = RULES_PATH) -> KopisRules:
    if not path.exists():
        return KopisRules()
    return KopisRules.from_data(json.loads(path.read_text(encoding="utf-8")))


class TTLCache:
    def __init__(self, clock: Callable[[], float] = _time.monotonic, max_items: int = 5000) -> None:
        self._clock = clock
        self._max = max_items
        self._items: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any:
        hit = self._items.get(key)
        if hit is None:
            return _MISSING
        if hit[0] <= self._clock():
            del self._items[key]
            return _MISSING
        return hit[1]

    def put(self, key: str, value: Any, ttl_s: float) -> None:
        if len(self._items) >= self._max:
            now = self._clock()
            self._items = {k: v for k, v in self._items.items() if v[0] > now}
            if len(self._items) >= self._max:
                self._items.clear()
        self._items[key] = (self._clock() + ttl_s, value)

    def __contains__(self, key: str) -> bool:
        return self.get(key) is not _MISSING


# --- XML → dataclasses (pure) ------------------------------------------------------------------


def _text(node: ET.Element, tag: str) -> str | None:
    value = (node.findtext(tag) or "").strip()
    return value or None


def _date(value: str | None) -> date | None:
    for fmt in ("%Y.%m.%d", "%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(value or "", fmt).date()
        except ValueError:
            continue
    return None


def _float(value: str | None) -> float | None:
    try:
        return float(value) if value else None
    except ValueError:
        return None


def _https(url: str | None) -> str | None:
    """Posters are served over https as well; http would be blocked as mixed content on the web."""
    return url.replace("http://", "https://", 1) if url else None


def _rows(xml: str | bytes) -> list[ET.Element]:
    """`<dbs><db>…</db></dbs>`; an error answer is a `<db>` with `<returncode>` and no ids."""
    try:
        root = ET.fromstring(xml)  # trusted official host only
    except ET.ParseError:
        return []
    return [db for db in root.iter("db") if db.find("returncode") is None]


def upstream_error(xml: str | bytes) -> str | None:
    """The message of an error document (`<returncode>` + `<errmsg>`), else None. Never contains the key."""
    try:
        root = ET.fromstring(xml)  # trusted official host only
    except ET.ParseError:
        return None
    for db in root.iter("db"):
        if db.find("returncode") is not None:
            return (db.findtext("errmsg") or db.findtext("returncode") or "error").strip()
    return None


def parse_list(xml: str | bytes) -> list[PerformanceSummary]:
    out: list[PerformanceSummary] = []
    for db in _rows(xml):
        pid, title = _text(db, "mt20id"), _text(db, "prfnm")
        if not pid or not title:
            continue
        out.append(
            PerformanceSummary(
                id=pid,
                title=title,
                date_from=_date(_text(db, "prfpdfrom")),
                date_to=_date(_text(db, "prfpdto")),
                venue_name=_text(db, "fcltynm") or "",
                poster_url=_https(_text(db, "poster")),
                area=_text(db, "area"),
                genre=_text(db, "genrenm"),
                state=_text(db, "prfstate"),
            )
        )
    return out


def parse_detail(xml: str | bytes) -> PerformanceDetail | None:
    for db in _rows(xml):
        pid, title = _text(db, "mt20id"), _text(db, "prfnm")
        if not pid or not title:
            continue
        return PerformanceDetail(
            id=pid,
            title=title,
            date_from=_date(_text(db, "prfpdfrom")),
            date_to=_date(_text(db, "prfpdto")),
            venue_name=_text(db, "fcltynm") or "",
            venue_id=_text(db, "mt10id"),
            runtime_text=_text(db, "prfruntime"),
            price_text=_text(db, "pcseguidance"),
            showtimes_text=_text(db, "dtguidance"),
            poster_url=_https(_text(db, "poster")),
            genre=_text(db, "genrenm"),
            state=_text(db, "prfstate"),
        )
    return None


def parse_venue(xml: str | bytes) -> Venue | None:
    for db in _rows(xml):
        vid = _text(db, "mt10id")
        if not vid:
            continue
        return Venue(
            id=vid,
            name=_text(db, "fcltynm") or "",
            address=_text(db, "adres"),
            lat=_float(_text(db, "la")),
            lng=_float(_text(db, "lo")),
        )
    return None


# --- client ------------------------------------------------------------------------------------


class KopisClient:
    def __init__(
        self,
        api_key: str | None,
        rules: KopisRules | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], float] = _time.monotonic,
    ) -> None:
        self._key = (api_key or "").strip()
        self.rules = rules or load_rules()
        self._transport = transport
        self._cache = TTLCache(clock)
        self._venue_id_by_name: dict[str, str] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self.upstream_calls = 0  # how many real requests were made (budgeting, tests)
        # KOPIS answers a bad or unregistered key with HTTP 200 and an error document. Swallowing it
        # would tell the user "nothing is on tonight" when the truth is "we are not allowed to ask".
        self.last_error: str | None = None

    @property
    def available(self) -> bool:
        return bool(self._key)

    def is_cached(self, kind: str, ident: str) -> bool:
        return f"{kind}:{ident}" in self._cache

    def known_venue_id(self, venue_name: str) -> str | None:
        """Learned from earlier detail answers: lets the caller skip the detail call of a performance
        whose venue is already known to be too far away."""
        return self._venue_id_by_name.get(venue_name)

    async def _get(self, path: str, params: Mapping[str, str]) -> bytes | None:
        self.upstream_calls += 1
        try:
            async with httpx.AsyncClient(
                timeout=self.rules.timeout_s, transport=self._transport, follow_redirects=True
            ) as client:
                resp = await client.get(
                    f"{self.rules.base_url}/{path}", params={"service": self._key, **params}
                )
                resp.raise_for_status()
                self.last_error = upstream_error(resp.content) or self.last_error
                return resp.content
        except httpx.HTTPError as exc:
            # never log the exception text or the URL: both carry the key
            log.warning("kopis request failed: %s %s", path.split("/")[0], type(exc).__name__)
            return None

    async def _cached(
        self, key: str, ttl_s: float, path: str, params: Mapping[str, str], parse: Callable[[bytes], Any]
    ) -> Any:
        hit = self._cache.get(key)
        if hit is not _MISSING:
            return hit
        lock = self._locks.setdefault(key, asyncio.Lock())
        try:
            async with lock:  # concurrent page views share one upstream call
                hit = self._cache.get(key)
                if hit is not _MISSING:
                    return hit
                body = await self._get(path, params)
                if body is None:
                    return None  # a failure is not cached
                value = parse(body)
                self._cache.put(key, value, ttl_s)
                return value
        finally:
            self._locks.pop(key, None)

    async def list_performances(
        self, day_from: date, day_to: date, *, area_code: str | None = None, state: str | None = None
    ) -> list[PerformanceSummary]:
        if not self.available:
            return []
        out: list[PerformanceSummary] = []
        for page in range(1, self.rules.max_list_pages + 1):
            params = {
                "stdate": day_from.strftime("%Y%m%d"),
                "eddate": day_to.strftime("%Y%m%d"),
                "cpage": str(page),
                "rows": str(self.rules.rows),
            }
            if area_code:
                params["signgucode"] = area_code
            if state:
                params["prfstate"] = state
            key = "list:" + "|".join(f"{k}={v}" for k, v in sorted(params.items()))
            rows = await self._cached(key, self.rules.ttl_list_s, "pblprfr", params, parse_list)
            out.extend(rows or [])
            if not rows or len(rows) < self.rules.rows:
                break
        return out

    async def detail(self, performance_id: str) -> PerformanceDetail | None:
        if not self.available or not performance_id.isalnum():
            return None
        found = await self._cached(
            f"detail:{performance_id}", self.rules.ttl_detail_s, f"pblprfr/{performance_id}", {}, parse_detail
        )
        if isinstance(found, PerformanceDetail) and found.venue_id and found.venue_name:
            self._venue_id_by_name[found.venue_name] = found.venue_id
        return found if isinstance(found, PerformanceDetail) else None

    async def venue(self, venue_id: str) -> Venue | None:
        if not self.available or not venue_id.isalnum():
            return None
        found = await self._cached(
            f"venue:{venue_id}", self.rules.ttl_venue_s, f"prfplc/{venue_id}", {}, parse_venue
        )
        return found if isinstance(found, Venue) else None


_shared: dict[str, KopisClient] = {}


def shared_client(api_key: str | None) -> KopisClient:
    """One client (= one cache) per process and key."""
    key = (api_key or "").strip()
    if key not in _shared:
        _shared[key] = KopisClient(key)
    return _shared[key]
