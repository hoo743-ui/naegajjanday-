"""한국관광공사 TourAPI 4.0 (KorService2) — nationwide pull in a dozen calls.

The per-region provider (`providers/tourapi.py`) would need one call per region × page; the development
quota is 1,000 calls a day. `areaBasedList2` happily returns 5,000 rows a call, so the whole country
(관광지·문화시설·레포츠·음식점 + 축제) fits in ~12 calls. Raw pages are cached on disk: mapping rules can
be re-tuned and re-applied without spending quota.

What this source adds that the 표준데이터 files do not: **a real photo of the place** (94 % of rows),
culture venues and leisure sports. Rows that match a place we already have do not create a duplicate —
they enrich it (photo, phone). Photos are 공공누리 Type1/Type3: free to show with the source credited;
the web credits 한국관광공사 wherever a `tong.visitkorea.or.kr` image is shown.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator, Mapping
from datetime import date, datetime
from pathlib import Path
from typing import Any

import httpx

from app.infra.ingestion.bulk.common import BulkEvent, BulkPlace, BulkReport, in_korea
from app.infra.ingestion.bulk.price_prior import PricePrior
from app.infra.ingestion.providers.tourapi import BASE_URL, extract_items

PROVIDER = "tourapi"
ROWS_PER_CALL = 5000
CALL_GAP_S = 0.6
CACHE_DAYS = 7
PLACE_OP, FESTIVAL_OP = "areaBasedList2", "searchFestival2"


class TourApiError(RuntimeError):
    pass


def _get(
    client: httpx.Client, key: str, op: str, params: Mapping[str, str]
) -> tuple[list[dict[str, Any]], int]:
    resp = client.get(
        f"{BASE_URL}/{op}",
        params={
            "serviceKey": key,
            "MobileOS": "ETC",
            "MobileApp": "naegajjanday",
            "_type": "json",
            "numOfRows": str(ROWS_PER_CALL),
            **params,
        },
    )
    resp.raise_for_status()
    try:
        payload = resp.json()
    except ValueError as exc:  # an unregistered / not-yet-propagated key answers with an XML error page
        raise TourApiError(resp.text.replace(key, "***")[:300]) from exc
    header = (payload.get("response") or {}).get("header") or {}
    if header.get("resultCode") != "0000":
        raise TourApiError(f"{header.get('resultCode')}: {header.get('resultMsg')}")
    return extract_items(payload)


def _fresh(path: Path) -> bool:
    return path.exists() and (time.time() - path.stat().st_mtime) < CACHE_DAYS * 86400


def download(
    key: str, out_dir: Path, content_types: Mapping[str, str], festivals_from: date, *, force: bool = False
) -> dict[str, int]:
    """Writes `<type>_<page>.json` / `festival_<page>.json`; returns rows per kind. Cached for a week."""
    out_dir.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    jobs: list[tuple[str, str, dict[str, str]]] = [
        (code, PLACE_OP, {"contentTypeId": code, "arrange": "C"}) for code in content_types
    ]
    jobs.append(
        ("festival", FESTIVAL_OP, {"eventStartDate": festivals_from.strftime("%Y%m%d"), "arrange": "C"})
    )
    with httpx.Client(timeout=90) as client:
        for kind, op, params in jobs:
            first = out_dir / f"{kind}_1.json"
            if not force and _fresh(first):
                counts[kind] = sum(
                    len(json.loads(p.read_text("utf-8"))) for p in out_dir.glob(f"{kind}_*.json")
                )
                continue
            for stale in out_dir.glob(f"{kind}_*.json"):
                stale.unlink()
            page, got = 1, 0
            while True:
                items, total = _get(client, key, op, {**params, "pageNo": str(page)})
                (out_dir / f"{kind}_{page}.json").write_text(json.dumps(items, ensure_ascii=False), "utf-8")
                got += len(items)
                if not items or got >= total:
                    break
                page += 1
                time.sleep(CALL_GAP_S)
            counts[kind] = got
            time.sleep(CALL_GAP_S)
    return counts


def has_cache(raw_dir: Path) -> bool:
    return any(raw_dir.glob("*_1.json"))


def read_items(raw_dir: Path, kind: str) -> Iterator[dict[str, Any]]:
    for path in sorted(raw_dir.glob(f"{kind}_*.json")):
        yield from json.loads(path.read_text("utf-8"))


def _clean(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _https(url: str | None) -> str | None:
    """visitkorea serves the same file over https; http would be blocked as mixed content in production."""
    return url.replace("http://", "https://", 1) if url else None


def images_of(item: Mapping[str, Any]) -> list[str]:
    return [u for u in (_https(_clean(item.get("firstimage"))), _https(_clean(item.get("firstimage2")))) if u]


def category_for(item: Mapping[str, Any], rules: Mapping[str, Any]) -> str | None:
    """Most specific rule wins: lclsSystm3 (8 chars) → 6 → 4-char group → 2-char root. The old
    cat1~3 codes are blank on a third of the rows; the new classification is always filled.
    `null` in the rules means "not something a day course visits" (campsites, golf, fishing, clinics)."""
    code = str(item.get("lclsSystm3") or "")
    table: Mapping[str, Any] = rules.get("by_lcls", {})
    for key in (code, code[:6], code[:4], code[:2]):
        if key and key in table:
            value = table[key]
            return str(value) if value else None
    return None


def _sido_sigungu(address: str | None) -> tuple[str | None, str | None]:
    parts = (address or "").split()
    return (parts[0] if parts else None), (parts[1] if len(parts) > 1 else None)


def to_place(
    item: Mapping[str, Any],
    rules: Mapping[str, Any],
    prior: PricePrior | None,
    sido_aliases: Mapping[str, str],
) -> tuple[BulkPlace | None, str | None]:
    name = _clean(item.get("title"))
    try:
        lat, lng = float(item.get("mapy") or 0), float(item.get("mapx") or 0)
    except (TypeError, ValueError):
        return None, "bad_coord"
    if not name:
        return None, "no_name"
    if not in_korea(lat, lng):
        return None, "bad_coord"
    lowered = name.replace(" ", "")
    if any(word in lowered for word in rules.get("exclude_name_contains", [])):
        return None, "excluded_name"
    category = category_for(item, rules)
    if category is None:
        return None, "unmapped_category"
    address = " ".join(p for p in (_clean(item.get("addr1")), _clean(item.get("addr2"))) if p) or None
    sido_raw, sigungu = _sido_sigungu(address)
    sido = sido_aliases.get(sido_raw or "", sido_raw)
    free = category in set(rules.get("free_categories", []))
    price = None if free or prior is None else prior.estimate(category, sido, None, name)
    images = images_of(item)
    return (
        BulkPlace(
            provider=PROVIDER,
            external_id=str(item["contentid"]),
            name=name,
            category_code=category,
            lat=lat,
            lng=lng,
            sido=sido,
            sigungu=sigungu,
            address=address,
            road_address=address,
            phone=_clean(item.get("tel")),
            price_per_person=price,
            price_is_estimated=price is not None,
            is_free=free,
            thumbnail_url=images[0] if images else None,
            images=images,
            raw={
                k: item.get(k)
                for k in ("cat1", "cat2", "cat3", "contenttypeid", "cpyrhtDivCd", "modifiedtime")
            },
        ),
        None,
    )


def _yyyymmdd(value: Any) -> date | None:
    try:
        return datetime.strptime(str(value), "%Y%m%d").date()
    except ValueError:
        return None


def _event_category(item: Mapping[str, Any], rules: Mapping[str, Any]) -> str:
    code = str(item.get("lclsSystm3") or "")
    table: Mapping[str, str] = rules.get("festival_by_lcls", {})
    for key in (code, code[:6], code[:4]):
        if key in table:
            return str(table[key])
    return str(rules.get("festival_category", "culture.festival"))


def to_event(item: Mapping[str, Any], rules: Mapping[str, Any]) -> tuple[BulkEvent | None, str | None]:
    title = _clean(item.get("title"))
    starts, ends = _yyyymmdd(item.get("eventstartdate")), _yyyymmdd(item.get("eventenddate"))
    try:
        lat, lng = float(item.get("mapy") or 0), float(item.get("mapx") or 0)
    except (TypeError, ValueError):
        return None, "bad_coord"
    if not title or starts is None:
        return None, "no_title_or_date"
    if not in_korea(lat, lng):
        return None, "bad_coord"
    address = " ".join(p for p in (_clean(item.get("addr1")), _clean(item.get("addr2"))) if p) or None
    return (
        BulkEvent(
            provider=PROVIDER,
            external_id=str(item["contentid"]),
            title=title,
            category_code=_event_category(item, rules),
            lat=lat,
            lng=lng,
            starts_on=starts,
            ends_on=ends or starts,
            address=address,
            images=images_of(item),
        ),
        None,
    )


def iter_places(
    items: Iterator[dict[str, Any]],
    rules: Mapping[str, Any],
    prior: PricePrior | None,
    sido_aliases: Mapping[str, str],
    report: BulkReport,
) -> Iterator[BulkPlace]:
    for item in items:
        report.read += 1
        place, reason = to_place(item, rules, prior, sido_aliases)
        if place is None:
            report.skip(reason or "unknown")
            continue
        report.mapped += 1
        yield place


def iter_events(
    items: Iterator[dict[str, Any]], rules: Mapping[str, Any], report: BulkReport
) -> Iterator[BulkEvent]:
    for item in items:
        report.read += 1
        event, reason = to_event(item, rules)
        if event is None:
            report.skip(reason or "unknown")
            continue
        report.mapped += 1
        yield event
