"""TourAPI lodging (contentTypeId=32), nationwide — where to sleep on a trip of more than one day.

Same official source, download helper and one-week raw cache as `tourapi_bulk`; the pages are stored as
`stay_<page>.json` next to the other kinds. Lodging gets its own category family `stay.*` whose course
role is `STAY` — no course template has a slot with that role, so a hotel can never turn up as a stop of
a day course. Which classification code becomes which `stay.*` category is data:
`data/bulk/stay_rules.json`.

There is no price here on purpose. The list operation carries none, the reference room rates live in
`detailInfo2` (one call per place, tens of thousands of calls against a 1,000-a-day quota), and a
category prior would be a made-up number — so lodging is stored without a price and the API says so.

    uv run python -m app.infra.ingestion.bulk.tourapi_stay [--force]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import text

from app.core.config import get_settings
from app.infra.db.session import Database
from app.infra.ingestion.bulk import download as bulk_download
from app.infra.ingestion.bulk import tourapi_bulk
from app.infra.ingestion.bulk.common import BulkPlace, BulkReport, in_korea, load_json
from app.infra.ingestion.bulk.regions import RegionIndex
from app.infra.ingestion.bulk.writer import BulkWriter

PROVIDER = tourapi_bulk.PROVIDER  # one KTO content id space → one provider, one `place_source` key
KIND = "stay"
RULES_FILE = "stay_rules.json"
REGIONS_FILE = "regions_kr.json"
LOCK_RETRIES = 20
LOCK_WAIT_S = 15.0


class StayIngestError(RuntimeError):
    pass


def load_rules() -> dict[str, Any]:
    return load_json(RULES_FILE)


def download(key: str, out_dir: Path, content_type: str, *, force: bool = False) -> int:
    """Writes `stay_<page>.json`; returns the number of rows on disk. Cached for a week."""
    out_dir.mkdir(parents=True, exist_ok=True)
    if not force and tourapi_bulk._fresh(out_dir / f"{KIND}_1.json"):
        return sum(1 for _ in tourapi_bulk.read_items(out_dir, KIND))
    for stale in out_dir.glob(f"{KIND}_*.json"):
        stale.unlink()
    page, got = 1, 0
    with httpx.Client(timeout=90) as client:
        while True:
            items, total = tourapi_bulk._get(
                client,
                key,
                tourapi_bulk.PLACE_OP,
                {"contentTypeId": content_type, "arrange": "C", "pageNo": str(page)},
            )
            (out_dir / f"{KIND}_{page}.json").write_text(json.dumps(items, ensure_ascii=False), "utf-8")
            got += len(items)
            if not items or got >= total:
                break
            page += 1
            time.sleep(tourapi_bulk.CALL_GAP_S)
    return got


def has_cache(raw_dir: Path) -> bool:
    return any(raw_dir.glob(f"{KIND}_*.json"))


def category_for(item: Mapping[str, Any], name: str, rules: Mapping[str, Any]) -> str | None:
    """Most specific classification first (lclsSystm3 8 → 6 → 4 → 2 chars), then the old cat3, then a
    word in the name, then the default. `null` for a code = not a place to book a room (campsites)."""
    code = str(item.get("lclsSystm3") or "")
    by_lcls: Mapping[str, Any] = rules.get("by_lcls", {})
    for key in (code, code[:6], code[:4], code[:2]):
        if key and key in by_lcls:
            value = by_lcls[key]
            return str(value) if value else None
    by_cat3: Mapping[str, Any] = rules.get("by_cat3", {})
    cat3 = str(item.get("cat3") or "")
    if cat3 in by_cat3:
        value = by_cat3[cat3]
        return str(value) if value else None
    lowered = name.replace(" ", "").lower()
    for row in rules.get("by_name_contains", []):
        if any(str(word).lower() in lowered for word in row["words"]):
            return str(row["category"])
    default = rules.get("default_category")
    return str(default) if default else None


def to_stay(
    item: Mapping[str, Any], rules: Mapping[str, Any], sido_aliases: Mapping[str, str]
) -> tuple[BulkPlace | None, str | None]:
    name = tourapi_bulk._clean(item.get("title"))
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
    category = category_for(item, name, rules)
    if category is None:
        return None, "unmapped_category"
    parts = (tourapi_bulk._clean(item.get("addr1")), tourapi_bulk._clean(item.get("addr2")))
    address = " ".join(p for p in parts if p) or None
    sido_raw, sigungu = tourapi_bulk._sido_sigungu(address)
    images = tourapi_bulk.images_of(item)
    return (
        BulkPlace(
            provider=PROVIDER,
            external_id=str(item["contentid"]),
            name=name,
            category_code=category,
            lat=lat,
            lng=lng,
            sido=sido_aliases.get(sido_raw or "", sido_raw),
            sigungu=sigungu,
            address=address,
            road_address=address,
            phone=tourapi_bulk._clean(item.get("tel")),
            price_per_person=None,  # no official price in the list operation; never estimated
            price_is_estimated=False,
            is_free=False,
            thumbnail_url=images[0] if images else None,
            images=images,
            raw={
                k: item.get(k) for k in ("cat3", "lclsSystm3", "contenttypeid", "cpyrhtDivCd", "modifiedtime")
            },
        ),
        None,
    )


def iter_stays(
    items: Iterable[Mapping[str, Any]],
    rules: Mapping[str, Any],
    sido_aliases: Mapping[str, str],
    report: BulkReport,
) -> Iterator[BulkPlace]:
    for item in items:
        report.read += 1
        place, reason = to_stay(item, rules, sido_aliases)
        if place is None:
            report.skip(reason or "unknown")
            continue
        report.mapped += 1
        yield place


def _sido_aliases(spec: Mapping[str, Any]) -> dict[str, str]:
    return {alias: s["name"] for s in spec["sido"] for alias in (s["name"], *s.get("aliases", []))}


def _is_locked(exc: BaseException) -> bool:
    return "database is locked" in str(exc).lower()


async def load_stays(db: Database, raw_dir: Path, key: str | None, *, force: bool = False) -> BulkReport:
    rules = load_rules()
    spec = load_json(REGIONS_FILE)
    if key:
        print(
            f"tourapi lodging rows on disk: {download(key, raw_dir, str(rules['content_type']), force=force)}"
        )
    elif not has_cache(raw_dir):
        raise StayIngestError(
            "TOURAPI_SERVICE_KEY is not set and no lodging page is cached in " + str(raw_dir)
        )

    async with db.sessionmaker() as session:
        index = await RegionIndex.load(session, spec)
        writer = BulkWriter(session, PROVIDER, index)
        await writer.prepare()
        places = list(
            iter_stays(tourapi_bulk.read_items(raw_dir, KIND), rules, _sido_aliases(spec), writer.report)
        )
        missing = sorted({p.category_code for p in places if not writer.has_category(p.category_code)})
        if missing:
            raise StayIngestError(f"categories {missing} are not in the DB — run `seed-config` first")
        await writer.write_all(places)
        if session.get_bind().dialect.name == "sqlite":
            await session.execute(text("ANALYZE"))
            await session.commit()
    print(
        "by category: "
        + ", ".join(f"{c}={n}" for c, n in Counter(p.category_code for p in places).most_common())
    )
    print(f"with photo: {sum(1 for p in places if p.thumbnail_url)} / {len(places)}")
    return writer.report


async def _run(force: bool) -> BulkReport:
    settings = get_settings()
    raw_dir = bulk_download.default_raw_dir() / "tourapi"
    for attempt in range(1, LOCK_RETRIES + 1):
        db = Database(settings)
        try:
            # a retry re-reads the cache (no quota) and the upsert skips what an earlier try committed
            return await load_stays(db, raw_dir, settings.tourapi_service_key, force=force and attempt == 1)
        except Exception as exc:
            if not _is_locked(exc) or attempt == LOCK_RETRIES:
                raise
            print(f"database is locked (another job is writing) — retry {attempt}/{LOCK_RETRIES}")
            await asyncio.sleep(LOCK_WAIT_S)
        finally:
            await db.dispose()
    raise StayIngestError("unreachable")


def main() -> None:
    parser = argparse.ArgumentParser(description="TourAPI lodging (contentTypeId=32), nationwide")
    parser.add_argument("--force", action="store_true", help="ignore the one-week raw cache")
    args = parser.parse_args()
    report = asyncio.run(_run(args.force))
    print(f"[tourapi:stay] {report.line()}")


if __name__ == "__main__":
    main()
