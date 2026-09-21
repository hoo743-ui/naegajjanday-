"""JSON / CSV import. Seed data and admin uploads go through the same pipeline as the API providers."""

from __future__ import annotations

import csv
import json
from collections.abc import AsyncIterator
from datetime import date
from pathlib import Path
from typing import Any

from app.infra.ingestion.base import (
    NormalizedEvent,
    NormalizedHour,
    NormalizedMenu,
    NormalizedPlace,
    RawPlace,
    RegionRef,
)

WEEKDAYS, WEEKEND = (0, 1, 2, 3, 4), (5, 6)


class FileFormatError(ValueError):
    pass


def read_payload(path: Path) -> dict[str, Any]:
    """Returns {"region": slug|None, "places": [...], "events": [...]} for .json and .csv files."""
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            data = {"places": data}
        if not isinstance(data, dict) or not isinstance(data.get("places", []), list):
            raise FileFormatError(f"{path.name}: expected an object with a 'places' array")
        return data
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as fh:
            return {"places": [_csv_row(row) for row in csv.DictReader(fh)]}
    raise FileFormatError(f"{path.name}: unsupported file type (use .json or .csv)")


def _csv_row(row: dict[str, str]) -> dict[str, Any]:
    out: dict[str, Any] = {k: (v if v != "" else None) for k, v in row.items()}
    for key in ("lat", "lng"):
        out[key] = float(out[key]) if out.get(key) is not None else None
    if out.get("price_per_person") is not None:
        out["price_per_person"] = int(float(out["price_per_person"]))
    out["is_free"] = str(out.get("is_free") or "").lower() in {"1", "true", "y", "yes"}
    if out.get("tags"):  # "가성비:0.9|조용한"
        tags: dict[str, float] = {}
        for token in str(out["tags"]).split("|"):
            name, _, weight = token.partition(":")
            if name.strip():
                tags[name.strip()] = float(weight) if weight else 1.0
        out["tags"] = tags
    return out


class FileProvider:
    name = "file"

    def __init__(self, path: Path) -> None:
        self._path = path
        self._payload: dict[str, Any] | None = None

    @property
    def payload(self) -> dict[str, Any]:
        if self._payload is None:
            self._payload = read_payload(self._path)
        return self._payload

    @property
    def region_slug(self) -> str | None:
        slug = self.payload.get("region")
        return str(slug) if slug else None

    async def fetch(self, region: RegionRef, cursor: dict[str, Any] | None = None) -> AsyncIterator[RawPlace]:
        start = int((cursor or {}).get("index", 0))
        rows = [("place", r) for r in self.payload.get("places", [])]
        rows += [("event", r) for r in self.payload.get("events", [])]
        for i, (kind, row) in enumerate(rows):
            if i < start:
                continue
            ext = str(row.get("external_id") or f"{region.slug}:{kind}:{row.get('name') or row.get('title')}")
            yield RawPlace(provider=self.name, external_id=ext, raw=row, kind=kind)  # type: ignore[arg-type]

    def normalize(self, raw: RawPlace) -> NormalizedPlace | NormalizedEvent | None:
        r = raw.raw
        if r.get("lat") is None or r.get("lng") is None:
            return None
        if raw.kind == "event":
            if not r.get("title") or not r.get("starts_on") or not r.get("ends_on"):
                return None
            return NormalizedEvent(
                provider=self.name,
                external_id=raw.external_id,
                title=str(r["title"]),
                lat=float(r["lat"]),
                lng=float(r["lng"]),
                starts_on=date.fromisoformat(str(r["starts_on"])),
                ends_on=date.fromisoformat(str(r["ends_on"])),
                category_code=r.get("category"),
                description=r.get("description"),
                address=r.get("address"),
                price=r.get("price"),
                is_free=bool(r.get("is_free")),
                booking_url=r.get("booking_url"),
                images=list(r.get("images") or []),
            )
        if not r.get("name"):
            return None
        rating = r.get("rating") or {}
        sentiment = r.get("sentiment") or {}
        return NormalizedPlace(
            provider=self.name,
            external_id=raw.external_id,
            name=str(r["name"]),
            lat=float(r["lat"]),
            lng=float(r["lng"]),
            category_code=r.get("category"),
            address=r.get("address"),
            road_address=r.get("road_address"),
            phone=r.get("phone"),
            description=r.get("description"),
            thumbnail_url=r.get("thumbnail_url"),
            images=list(r.get("images") or []),
            price_per_person=r.get("price_per_person"),
            is_free=bool(r.get("is_free")),
            menus=[
                NormalizedMenu(str(m["name"]), int(m["price"]), bool(m.get("is_signature")))
                for m in r.get("menus") or []
            ],
            opening_hours=_hours(r.get("opening_hours") or []),
            popular_times=_popular(r.get("popular_times")),
            rating_avg=rating.get("avg"),
            rating_count=int(rating.get("count") or 0),
            sentiment_score=sentiment.get("score"),
            sentiment_count=int(sentiment.get("count") or 0),
            aspect_scores=dict(sentiment.get("aspects") or {}),
            tags=_tags(r.get("tags")),
        )


def _hours(rows: list[dict[str, Any]]) -> list[NormalizedHour]:
    out: dict[int, NormalizedHour] = {}
    for row in rows:
        dows = row.get("dow")
        for dow in dows if isinstance(dows, list) else [dows]:
            if dow is None or not 0 <= int(dow) <= 6:
                continue
            out[int(dow)] = NormalizedHour(
                dow=int(dow),
                open_time=row.get("open"),
                close_time=row.get("close"),
                break_start=row.get("break_start"),
                break_end=row.get("break_end"),
                is_closed=bool(row.get("is_closed")),
            )
    return [out[d] for d in sorted(out)]


def _popular(raw: Any) -> list[tuple[int, int, float]]:
    if not raw:
        return []
    if isinstance(raw, dict):  # {"weekday": [24], "weekend": [24]}
        out: list[tuple[int, int, float]] = []
        for key, dows in (("weekday", WEEKDAYS), ("weekend", WEEKEND)):
            curve = raw.get(key) or []
            out.extend((d, h, float(v)) for d in dows for h, v in enumerate(curve[:24]))
        return out
    return [(int(x["dow"]), int(x["hour"]), float(x["congestion"])) for x in raw]


def _tags(raw: Any) -> dict[str, float]:
    if isinstance(raw, dict):
        return {str(k): float(v) for k, v in raw.items()}
    if isinstance(raw, list):
        return {str(k): 1.0 for k in raw}
    return {}
