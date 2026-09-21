"""전국 표준데이터 CSV (data.go.kr): 도시공원 · 박물관/미술관 · 관광지 · 전통시장 → places,
문화축제 → events. Column names and inclusion rules are DATA (`bulk_rules.json` → "std")."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Iterator, Mapping
from datetime import date
from typing import Any

from app.infra.ingestion.base import NormalizedHour
from app.infra.ingestion.bulk.common import BulkEvent, BulkPlace, BulkReport, in_korea, to_float

KINDS = ("parks", "museums", "tourist", "markets", "festivals")
_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})")
_DOW_KR = "월화수목금토일"
MAX_FEE = 100_000


def _col(row: Mapping[str, str], columns: Mapping[str, str], field: str) -> str:
    return row.get(columns.get(field, ""), "").strip()


def _external_id(
    row: Mapping[str, str], columns: Mapping[str, str], name: str, lat: float, lng: float
) -> str:
    explicit = _col(row, columns, "external_id")
    if explicit:
        return explicit
    return hashlib.sha1(f"{name}|{lat:.5f}|{lng:.5f}".encode()).hexdigest()[:20]


def _hhmm(value: str) -> str | None:
    m = _TIME_RE.match(value)
    if m is None:
        return None
    hour, minute = int(m.group(1)), int(m.group(2))
    return f"{hour % 24:02d}:{minute:02d}" if hour <= 24 and minute < 60 else None


def parse_hours(row: Mapping[str, str], columns: Mapping[str, str]) -> list[NormalizedHour]:
    """Weekday / holiday visiting hours as published. "00:00–00:00" means "not stated" here, not 24 h."""
    weekday = (_hhmm(_col(row, columns, "weekday_open")), _hhmm(_col(row, columns, "weekday_close")))
    holiday = (_hhmm(_col(row, columns, "holiday_open")), _hhmm(_col(row, columns, "holiday_close")))
    if not all(weekday) or weekday[0] == weekday[1]:
        return []
    if not all(holiday) or holiday[0] == holiday[1]:
        holiday = weekday
    closed_info = _col(row, columns, "closed_info")
    closed = {i for i, ch in enumerate(_DOW_KR) if f"{ch}요일" in closed_info or f"매주 {ch}" in closed_info}
    hours: list[NormalizedHour] = []
    for dow in range(7):
        if dow in closed:
            hours.append(NormalizedHour(dow=dow, is_closed=True))
            continue
        open_time, close_time = weekday if dow < 5 else holiday
        hours.append(NormalizedHour(dow=dow, open_time=open_time, close_time=close_time))
    return hours


def _included(row: Mapping[str, str], spec: Mapping[str, Any]) -> bool:
    columns = spec["columns"]
    kind = _col(row, columns, "kind")
    include = spec.get("include_kinds")
    if include is not None:
        if kind not in include:
            return False
        if (to_float(_col(row, columns, "area")) or 0.0) < float(include[kind]):
            return False
    must = spec.get("kind_must_contain")
    return not (must and must not in kind)


def to_place(row: Mapping[str, str], spec: Mapping[str, Any]) -> tuple[BulkPlace | None, str | None]:
    columns = spec["columns"]
    name = _col(row, columns, "name")
    lat, lng = to_float(_col(row, columns, "lat")), to_float(_col(row, columns, "lng"))
    if not name:
        return None, "no_name"
    if lat is None or lng is None or not in_korea(lat, lng):
        return None, "no_coord"
    if not _included(row, spec):
        return None, "excluded_kind"
    category = str(spec["category"])
    for keyword, code in (spec.get("category_by_name") or {}).items():
        if keyword in name:
            category = str(code)
            break
    fee = to_float(_col(row, columns, "price")) if "price" in columns else None
    price = int(fee) if fee is not None and 0 < fee <= MAX_FEE else None
    is_free = bool(spec.get("is_free")) or (fee is not None and fee == 0)
    place = BulkPlace(
        provider=str(spec["provider"]),
        external_id=_external_id(row, columns, name, lat, lng),
        name=name,
        category_code=category,
        lat=lat,
        lng=lng,
        address=_col(row, columns, "address") or None,
        road_address=_col(row, columns, "road_address") or None,
        phone=_col(row, columns, "phone") or None,
        description=_col(row, columns, "description") or None,
        price_per_person=price,
        price_is_estimated=False,
        is_free=is_free,
        hours=parse_hours(row, columns),
        raw={"kind": _col(row, columns, "kind")},
    )
    return place, None


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def to_event(row: Mapping[str, str], spec: Mapping[str, Any]) -> tuple[BulkEvent | None, str | None]:
    columns = spec["columns"]
    title = _col(row, columns, "name")
    lat, lng = to_float(_col(row, columns, "lat")), to_float(_col(row, columns, "lng"))
    starts, ends = _parse_date(_col(row, columns, "starts_on")), _parse_date(_col(row, columns, "ends_on"))
    if not title:
        return None, "no_name"
    if lat is None or lng is None or not in_korea(lat, lng):
        return None, "no_coord"
    if starts is None or ends is None or ends < starts:
        return None, "bad_dates"
    venue = _col(row, columns, "venue")
    address = _col(row, columns, "road_address") or _col(row, columns, "address")
    digest = hashlib.sha1(f"{title}|{starts.isoformat()}|{lat:.5f}|{lng:.5f}".encode()).hexdigest()[:20]
    return (
        BulkEvent(
            provider=str(spec["provider"]),
            external_id=digest,
            title=title,
            category_code=str(spec["category"]),
            lat=lat,
            lng=lng,
            starts_on=starts,
            ends_on=ends,
            description=_col(row, columns, "description") or None,
            address=" ".join(x for x in (address, f"({venue})" if venue else "") if x) or None,
            booking_url=_col(row, columns, "url") or None,
        ),
        None,
    )


def iter_places(
    rows: Iterable[Mapping[str, str]], spec: Mapping[str, Any], report: BulkReport
) -> Iterator[BulkPlace]:
    for row in rows:
        report.read += 1
        place, reason = to_place(row, spec)
        if place is None:
            report.skip(reason or "invalid")
            continue
        report.mapped += 1
        yield place


def iter_events(
    rows: Iterable[Mapping[str, str]], spec: Mapping[str, Any], report: BulkReport
) -> Iterator[BulkEvent]:
    for row in rows:
        report.read += 1
        event, reason = to_event(row, spec)
        if event is None:
            report.skip(reason or "invalid")
            continue
        report.mapped += 1
        yield event
