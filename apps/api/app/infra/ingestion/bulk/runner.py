"""Orchestration of the bulk loaders (called by `python -m app.cli ingest-bulk …`)."""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, insert, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.db.base import utcnow
from app.infra.db.models import Category, Event, Place, PlaceSource, PlaceTag, Region, Tag
from app.infra.db.session import Database
from app.infra.ingestion import dedupe
from app.infra.ingestion.bulk import goodprice, official_marks, semas_store, std_datasets, tourapi_bulk
from app.infra.ingestion.bulk.common import (
    BulkEvent,
    BulkPlace,
    BulkReport,
    GridIndex,
    chunked,
    iter_csv,
    load_json,
)
from app.infra.ingestion.bulk.price_prior import PricePrior
from app.infra.ingestion.bulk.regions import RegionIndex, build_region_rows, upsert_generated_regions
from app.infra.ingestion.bulk.writer import BulkWriter

Log = Callable[[str], None]
FOOD_ROLES = ("MEAL", "CAFE", "DESSERT", "BAR")
SIGHT_ROLES = ("ATTRACTION", "CULTURE", "NIGHTVIEW")
PROGRESS_EVERY = 50_000


class BulkIngestError(RuntimeError):
    pass


def _sido_aliases(spec: dict[str, Any]) -> dict[str, str]:
    return {alias: s["name"] for s in spec["sido"] for alias in (s["name"], *s.get("aliases", []))}


async def _semas_mapper(session: AsyncSession, spec: dict[str, Any]) -> semas_store.SemasMapper:
    categories = (await session.execute(select(Category.code, Category.provider_mapping))).all()
    mapping = semas_store.code_to_category((code, pm) for code, pm in categories)
    if not mapping:
        raise BulkIngestError("no category has provider_mapping.semas — run `seed-config` first")
    prior = PricePrior.from_data(load_json("price_prior.json"), spec)
    return semas_store.SemasMapper.from_data(mapping, load_json("bulk_rules.json"), prior)


async def _finish(session: AsyncSession) -> None:
    """Fresh planner statistics: without them SQLite may pick a poor index for the bbox query."""
    if session.get_bind().dialect.name == "sqlite":
        await session.execute(text("ANALYZE"))
        await session.commit()


async def load_semas(
    db: Database,
    path: Path,
    *,
    only: Sequence[str] = (),
    regions: bool = True,
    close_unseen: bool = False,
    log: Log = print,
) -> BulkReport:
    spec = load_json("regions_kr.json")
    members = semas_store.ordered_members(path, only)
    if not members:
        raise BulkIngestError(f"no CSV found in {path} (filter: {list(only) or 'none'})")
    async with db.sessionmaker() as session:
        mapper = await _semas_mapper(session, spec)
        if regions:
            log(f"pass 1/2: deriving regions from {len(members)} file(s)…")
            stats = semas_store.collect_region_stats(path, mapper, members)
            rows = build_region_rows(spec, stats)
            await upsert_generated_regions(session, rows)
            await session.commit()
            log(f"regions upserted: {len(rows)}")
        index = await RegionIndex.load(session, spec)
        writer = BulkWriter(session, semas_store.PROVIDER, index)
        await writer.prepare()
        log("pass 2/2: loading stores…")
        sidos: set[str] = set()

        def tracked() -> Any:
            for place in semas_store.iter_places(path, mapper, writer.report, members):
                if place.sido:
                    sidos.add(place.sido)
                if writer.report.mapped % PROGRESS_EVERY == 0:
                    log(f"  … {writer.report.line()}")
                yield place

        await writer.write_all(tracked())
        if close_unseen:
            await writer.close_unseen(sidos)
        await _finish(session)
    return writer.report


def admin_from_address(address: str | None) -> tuple[str | None, str | None]:
    """'경기도 수원시 팔달구 …' → ('경기도', '수원시 팔달구'); '서울특별시 마포구 …' → (…, '마포구')."""
    tokens = (address or "").split()
    if len(tokens) < 2:
        return None, None
    sigungu = tokens[1]
    if len(tokens) >= 3 and tokens[1].endswith("시") and tokens[2].endswith(("구", "군")):
        sigungu = f"{tokens[1]} {tokens[2]}"
    return tokens[0], sigungu


async def reassign_regions(session: AsyncSession, spec: dict[str, Any], *, log: Log = print) -> int:
    """Recompute `place.region_id` for every place (after regions or hotspots changed).

    The loaders skip rows whose content hash is unchanged, so they never move a place to another
    region — this does, streaming ids and updating only the rows whose region really changed.
    """
    index = await RegionIndex.load(session, spec)
    moves: list[dict[str, int]] = []
    seen = 0
    stmt = select(Place.id, Place.lat, Place.lng, Place.region_id, Place.road_address, Place.address)
    rows = (await session.execute(stmt)).all()  # ids + two floats + addresses: fine for ~1M rows
    for pid, lat, lng, region_id, road_address, address in rows:
        seen += 1
        sido, sigungu = admin_from_address(road_address or address)
        target = index.locate(lat, lng, sido, sigungu)
        if target is not None and target != region_id:
            moves.append({"id": pid, "region_id": target})
    for start in range(0, len(moves), 5000):
        await session.execute(update(Place), moves[start : start + 5000])
        await session.commit()
    log(f"places checked: {seen:,}; moved to another region: {len(moves):,}")
    return len(moves)


async def rebuild_regions(db: Database, path: Path, *, log: Log = print) -> int:
    """Pass 1 of the store load only (derive 시도/시군구/핫스팟 rows), then re-home every place."""
    spec = load_json("regions_kr.json")
    members = semas_store.ordered_members(path, ())
    if not members:
        raise BulkIngestError(f"no CSV found in {path}")
    async with db.sessionmaker() as session:
        mapper = await _semas_mapper(session, spec)
        log(f"deriving regions from {len(members)} file(s)…")
        region_stats = semas_store.collect_region_stats(path, mapper, members)
        rows = build_region_rows(spec, region_stats)
        await upsert_generated_regions(session, rows)
        await session.commit()
        log(f"regions upserted: {len(rows)}")
        moved = await reassign_regions(session, spec, log=log)
        await _finish(session)
    return moved


async def _existing_index(
    session: AsyncSession, roles: Sequence[str], cells: set[tuple[int, int]], not_provider: str
) -> GridIndex:
    """Only the buckets we are going to look at — never the whole table in memory."""
    index = GridIndex()
    own = select(PlaceSource.place_id).where(
        PlaceSource.provider == not_provider, PlaceSource.match_confidence >= 1.0
    )
    stmt = (
        select(Place.id, Place.name, Place.lat, Place.lng, Place.phone)
        .join(Category, Category.id == Place.category_id)
        .where(Category.course_role.in_(roles), Place.status == "approved", Place.id.not_in(own))
        .execution_options(yield_per=20_000)
    )
    async for pid, name, lat, lng, phone in await session.stream(stmt):
        if index.cell_of(lat, lng) in cells:
            index.add(dedupe.ExistingPlace(pid, name, lat, lng, phone))
    return index


async def load_goodprice(db: Database, path: Path, store_path: Path, *, log: Log = print) -> BulkReport:
    spec = load_json("regions_kr.json")
    rules = load_json("bulk_rules.json")["goodprice"]
    aliases = _sido_aliases(spec)
    async with db.sessionmaker() as session:
        index = await RegionIndex.load(session, spec)
        writer = BulkWriter(session, goodprice.PROVIDER, index)
        await writer.prepare()
        rows = goodprice.parse_rows(iter_csv(path), rules, writer.report, aliases)
        log(f"good-price food rows with a road address: {len(rows)}; joining with {store_path.name}…")
        coords = goodprice.building_coords(iter_csv(store_path), {r.key for r in rows}, aliases)
        log(f"addresses found in the store file: {len(coords)}")
        probe = GridIndex()
        cells = {cell for lat, lng in coords.values() for cell in probe.neighbourhood(lat, lng)}
        existing = await _existing_index(session, FOOD_ROLES, cells, goodprice.PROVIDER)
        categories = (await session.execute(select(Category.code, Category.provider_mapping))).all()
        by_kind = {
            str(kind): code for code, pm in categories for kind in (pm or {}).get(goodprice.MAPPING_KEY) or []
        }
        places = [
            p
            for p in goodprice.to_places(rows, coords, existing, by_kind, rules, writer.report)
            if writer.has_category(p.category_code)
        ]
        await writer.write_all(places)
        await _finish(session)
    return writer.report


async def load_std(db: Database, kind: str, path: Path, *, log: Log = print) -> BulkReport:
    specs = load_json("bulk_rules.json")["std"]
    if kind not in specs:
        raise BulkIngestError(f"unknown kind '{kind}' (choose from {', '.join(std_datasets.KINDS)})")
    spec = specs[kind]
    async with db.sessionmaker() as session:
        index = await RegionIndex.load(session, load_json("regions_kr.json"))
        writer = BulkWriter(session, str(spec["provider"]), index)
        await writer.prepare()
        if spec.get("event"):
            await writer.write_events(list(std_datasets.iter_events(iter_csv(path), spec, writer.report)))
            return writer.report
        candidates = list(std_datasets.iter_places(iter_csv(path), spec, writer.report))
        probe = GridIndex()
        cells = {cell for p in candidates for cell in probe.neighbourhood(p.lat, p.lng)}
        existing = await _existing_index(session, SIGHT_ROLES, cells, str(spec["provider"]))
        keep: list[BulkPlace] = []
        for p in candidates:
            if not writer.has_category(p.category_code):
                writer.report.skip("unknown_category")
            elif existing.find_match(p.name, p.lat, p.lng, p.phone) is not None:
                writer.report.skip("duplicate_of_other_source")  # e.g. a park also listed as 관광지
            else:
                keep.append(p)
        log(f"{kind}: {len(keep)} rows to upsert")
        await writer.write_all(keep)
        await _finish(session)
    return writer.report


MARK_CHUNK = 5000
ID_CHUNK = 900  # stays below SQLite's bound-parameter limit on old builds


def mark_kinds() -> list[str]:
    return [k for k in load_json("bulk_rules.json")["marks"] if not k.startswith("_")]


async def load_marks(db: Database, kind: str, path: Path, *, log: Log = print) -> BulkReport:
    """백년가게 · 모범음식점 · 인허가(업력, 단란/유흥주점) → tags / hidden status on places we already have.

    Re-runnable: everything this mark wrote last time (its `place_source` rows, the tags on those
    places, the places it hid) is taken back first, so a revoked designation or a closed licence
    disappears with the next file."""
    specs = load_json("bulk_rules.json")["marks"]
    if kind not in specs or kind.startswith("_"):
        raise BulkIngestError(f"unknown mark '{kind}' (choose from {', '.join(mark_kinds())})")
    spec = specs[kind]
    provider = str(spec["provider"])
    aliases = _sido_aliases(load_json("regions_kr.json"))
    report = BulkReport()
    today = date.today()
    async with db.sessionmaker() as session:
        index = official_marks.PlaceAddressIndex()
        stmt = (
            select(Place.id, Place.name, Place.road_address, Place.address)
            .where(Place.status.in_(("approved", "hidden")))
            .execution_options(yield_per=20_000)
        )
        async for pid, name, road_address, address in await session.stream(stmt):
            index.add(pid, name, road_address or address, aliases)
        log(f"{kind}: {len(index):,} buildings with a place; reading {path.name}…")
        matches = official_marks.match_rows(
            official_marks.iter_rows(iter_csv(path), spec, report, aliases),
            index,
            float(spec.get("name_match_min", 0.75)),
            report,
        )
        log(f"{kind}: {len(matches):,} places matched")

        tag_names = [str(spec["tag"])] if spec.get("tag") else []
        tag_names += [str(r["tag"]) for r in spec.get("age_tags", [])]
        tag_ids: dict[str, int] = {}
        for tag_name in tag_names:
            tag_id = await session.scalar(select(Tag.id).where(Tag.name == tag_name))
            if tag_id is None:
                tag = Tag(name=tag_name, group="feature", is_selectable=False)
                session.add(tag)
                await session.flush()
                tag_id = tag.id
            tag_ids[tag_name] = tag_id

        # take back what the previous run of this mark wrote
        previous = (
            await session.execute(
                select(PlaceSource.place_id, PlaceSource.raw).where(
                    PlaceSource.provider == provider, PlaceSource.place_id.is_not(None)
                )
            )
        ).all()
        keep_hidden = {m.place_id for m in matches} if spec.get("hide") else set()
        unhide = [pid for pid, raw in previous if (raw or {}).get("hidden") and pid not in keep_hidden]
        if tag_ids:
            for id_chunk in chunked([pid for pid, _raw in previous], ID_CHUNK):
                await session.execute(
                    delete(PlaceTag).where(
                        PlaceTag.place_id.in_(id_chunk),
                        PlaceTag.tag_id.in_(list(tag_ids.values())),
                        PlaceTag.source == "provider",
                    )
                )
        for id_chunk in chunked(unhide, ID_CHUNK):
            await session.execute(
                update(Place).where(Place.id.in_(id_chunk), Place.status == "hidden").values(status="approved")
            )
        report.reopened += len(unhide)
        await session.execute(delete(PlaceSource).where(PlaceSource.provider == provider))

        # tags — never on top of a tag an admin (or another mark) already put there
        wanted = [
            (m.place_id, tag_ids[tag_name], weight)
            for m in matches
            for tag_name, weight in official_marks.tags_for(m, spec, today).items()
        ]
        taken: set[tuple[int, int]] = set()
        if wanted:
            pairs = await session.execute(
                select(PlaceTag.place_id, PlaceTag.tag_id).where(PlaceTag.tag_id.in_(list(tag_ids.values())))
            )
            taken = {(pid, tid) for pid, tid in pairs}
        tag_rows = [
            {"place_id": pid, "tag_id": tid, "weight": weight, "source": "provider"}
            for pid, tid, weight in wanted
            if (pid, tid) not in taken
        ]
        for tag_chunk in chunked(tag_rows, MARK_CHUNK):
            await session.execute(insert(PlaceTag), list(tag_chunk))

        hidden: set[int] = set()
        if spec.get("hide"):
            for id_chunk in chunked([m.place_id for m in matches], ID_CHUNK):
                await session.execute(
                    update(Place).where(Place.id.in_(id_chunk), Place.status == "approved").values(status="hidden")
                )
                hidden.update(id_chunk)
            report.closed += len(hidden)

        now = utcnow()
        source_rows = [
            {
                "provider": provider,
                "external_id": m.row.external_id,
                "place_id": m.place_id,
                "raw": {**m.row.raw, **({"hidden": True} if m.place_id in hidden else {})},
                "fetched_at": now,
                "content_hash": m.content_hash,
                "match_confidence": min(0.99, m.similarity),  # < 1.0: an enrichment, never the owner
            }
            for m in matches
        ]
        for source_chunk in chunked(source_rows, MARK_CHUNK):
            await session.execute(insert(PlaceSource), list(source_chunk))
        await session.commit()
        report.merged = len(matches)
        report.created = len(tag_rows)
        log(f"{kind}: tags written {len(tag_rows):,}; hidden {len(hidden):,}; un-hidden {len(unhide):,}")
        await _finish(session)
    return report


TOURAPI_FOOD_PREFIXES = ("food", "cafe", "dessert", "bar")
TOURAPI_SIGHT_ROLES = (*SIGHT_ROLES, "ACTIVITY")
_EVENT_NOISE = re.compile(r"(제\s*\d+\s*회|\d{4}\s*년?|[\s\W_]+)")


def _event_key(title: str) -> str:
    """Festival identity across sources: "제17회 광주국제아트페어" and "2026 광주국제아트페어" match."""
    return _EVENT_NOISE.sub("", title).lower()


async def load_tourapi(
    db: Database, raw_dir: Path, key: str | None, *, force: bool = False, log: Log = print
) -> dict[str, BulkReport]:
    """Nationwide TourAPI: real photos for places we already have, plus culture / leisure / festivals.

    Downloads at most once a week (raw pages are cached in `raw_dir`), so re-tuning
    `bulk_rules.json › tourapi` and re-running costs no quota."""
    rules = load_json("bulk_rules.json")["tourapi"]
    spec = load_json("regions_kr.json")
    aliases = _sido_aliases(spec)
    prior = PricePrior.from_data(load_json("price_prior.json"), spec)
    if key:
        counts = tourapi_bulk.download(
            key, raw_dir, rules["content_types"], date.fromisoformat(rules["festivals_from"]), force=force
        )
        log(f"tourapi rows on disk: {counts}")
    elif not tourapi_bulk.has_cache(raw_dir):
        raise BulkIngestError("TOURAPI_SERVICE_KEY is not set and nothing is cached in " + str(raw_dir))

    reports: dict[str, BulkReport] = {}
    async with db.sessionmaker() as session:
        index = await RegionIndex.load(session, spec)
        writer = BulkWriter(session, tourapi_bulk.PROVIDER, index)
        await writer.prepare()
        for code, label in rules["content_types"].items():
            before = replace(writer.report, skip_reasons=dict(writer.report.skip_reasons))
            candidates = [
                p
                for p in tourapi_bulk.iter_places(
                    tourapi_bulk.read_items(raw_dir, code), rules, prior, aliases, writer.report
                )
            ]
            probe = GridIndex()
            cells = {cell for p in candidates for cell in probe.neighbourhood(p.lat, p.lng)}
            food = [p for p in candidates if p.category_code.startswith(TOURAPI_FOOD_PREFIXES)]
            roles = FOOD_ROLES if len(food) * 2 > len(candidates) else TOURAPI_SIGHT_ROLES
            existing = await _existing_index(session, roles, cells, tourapi_bulk.PROVIDER)
            keep: list[BulkPlace] = []
            for p in candidates:
                if not writer.has_category(p.category_code):
                    writer.report.skip("unknown_category")
                    continue
                match = existing.find_match(p.name, p.lat, p.lng, p.phone)
                if match is not None:  # we already have this place → give it its photo, keep one row
                    p.merge_into_place_id = match.place_id
                keep.append(p)
            enrich = sum(1 for p in keep if p.merge_into_place_id is not None)
            log(f"{label}: {len(keep)} rows ({enrich} enrich an existing place, {len(keep) - enrich} new)")
            await writer.write_all(keep)
            reports[label] = _delta(before, writer.report)

        # festivals: the 표준데이터 file often has the same festival without a photo
        before = replace(writer.report, skip_reasons=dict(writer.report.skip_reasons))
        events = list(
            tourapi_bulk.iter_events(tourapi_bulk.read_items(raw_dir, "festival"), rules, writer.report)
        )
        others = (
            await session.execute(
                select(Event.id, Event.title, Event.starts_on, Event.ends_on, Event.images).where(
                    Event.provider != tourapi_bulk.PROVIDER
                )
            )
        ).all()
        by_key: dict[str, list[Any]] = {}
        for row in others:
            by_key.setdefault(_event_key(row.title), []).append(row)
        fresh: list[BulkEvent] = []
        photo_updates: list[dict[str, Any]] = []
        for e in events:
            twin = next(
                (
                    r
                    for r in by_key.get(_event_key(e.title), [])
                    if r.starts_on <= e.ends_on and e.starts_on <= r.ends_on
                ),
                None,
            )
            if twin is None:
                fresh.append(e)
                continue
            writer.report.merged += 1
            if e.images and not twin.images:
                photo_updates.append({"id": twin.id, "images": list(e.images)})
        if photo_updates:
            await session.execute(update(Event), photo_updates)
            await session.commit()
        await writer.write_events(fresh)
        known = len(events) - len(fresh)
        log(f"축제: {len(fresh)} new, {known} already known ({len(photo_updates)} got a photo)")
        reports["축제"] = _delta(before, writer.report)
        await _finish(session)
    return reports


def _delta(before: BulkReport, after: BulkReport) -> BulkReport:
    """What one content type contributed (the writer keeps a running total)."""
    out = BulkReport()
    for name in (
        "read",
        "mapped",
        "created",
        "updated",
        "unchanged",
        "merged",
        "skipped",
        "closed",
        "reopened",
    ):
        setattr(out, name, getattr(after, name) - getattr(before, name))
    for reason, count in after.skip_reasons.items():
        if count - before.skip_reasons.get(reason, 0):
            out.skip_reasons[reason] = count - before.skip_reasons.get(reason, 0)
    return out


async def stats(db: Database) -> dict[str, Any]:
    async with db.sessionmaker() as session:
        by_role = (
            await session.execute(
                select(Category.course_role, func.count(Place.id))
                .join(Place, Place.category_id == Category.id)
                .where(Place.status == "approved")
                .group_by(Category.course_role)
            )
        ).all()
        level1 = {r.id: r for r in (await session.scalars(select(Region))).all()}

        def top(region_id: int) -> str:
            region = level1[region_id]
            hops = 0  # a corrupt tree (a region that is its own ancestor) must not hang the report
            while region.parent_id is not None and region.parent_id in level1 and hops < 8:
                region, hops = level1[region.parent_id], hops + 1
            return region.name

        by_sido: dict[str, int] = {}
        per_region = await session.execute(
            select(Place.region_id, func.count(Place.id))
            .where(Place.status == "approved")
            .group_by(Place.region_id)
        )
        for region_id, n in per_region:
            by_sido[top(region_id)] = by_sido.get(top(region_id), 0) + n
        priced = (
            await session.execute(
                select(Place.price_is_estimated, Place.is_free, func.count(Place.id))
                .where(Place.status == "approved")
                .group_by(Place.price_is_estimated, Place.is_free)
            )
        ).all()
        measured = await session.scalar(
            select(func.count(Place.id)).where(
                Place.status == "approved",
                Place.price_is_estimated.is_(False),
                Place.price_per_person.is_not(None),
            )
        )
        providers = (
            await session.execute(select(PlaceSource.provider, func.count()).group_by(PlaceSource.provider))
        ).all()
        regions_by_level = (
            await session.execute(select(Region.level, func.count()).group_by(Region.level))
        ).all()
        events = await session.scalar(select(func.count(Event.id)))
    return {
        "places_by_role": {role: n for role, n in by_role},
        "places_by_sido": dict(sorted(by_sido.items(), key=lambda t: -t[1])),
        "price": {
            "estimated": sum(n for est, _free, n in priced if est),
            "measured": int(measured or 0),
            "free": sum(n for _est, free, n in priced if free),
        },
        "sources": {p: n for p, n in providers},
        "regions_by_level": {int(level): n for level, n in regions_by_level},
        "events": int(events or 0),
    }
