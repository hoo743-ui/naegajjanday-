"""Pro-baseball home stadiums as places (`data/sports/kbo_stadiums.json`).

There is no official open API for the game schedule, and scraping the league site is against our rules.
So only the stadiums are registered; "is there a game today" is a plain link to the official schedule
page that the web shows next to the place. Nothing here fetches or parses that page, and the engine
never claims that a game exists.

A stadium that the nationwide data already has (same spot, same name) is not duplicated: the existing
place is promoted to the stadium category and keeps its photo / phone.

Run from apps/api (idempotent):  uv run python -m app.infra.ingestion.bulk.venues
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import API_ROOT, get_settings
from app.infra.db.models import Category, Place, PlaceSource
from app.infra.db.session import Database
from app.infra.ingestion.bulk.common import BulkPlace, BulkReport, load_json
from app.infra.ingestion.bulk.price_prior import PricePrior
from app.infra.ingestion.bulk.regions import RegionIndex
from app.infra.ingestion.bulk.writer import BulkWriter
from app.infra.ingestion.dedupe import ExistingPlace, distance_m
from app.infra.ingestion.price import price_tier

Log = Callable[[str], None]
DATA_PATH = API_ROOT / "data" / "sports" / "kbo_stadiums.json"
DEG_PER_M = 1 / 111_000  # bbox pre-filter only; the real distance check follows
LOCK_RETRIES = 8
LOCK_WAIT_S = 5.0


class VenueIngestError(RuntimeError):
    pass


def load_spec(path: Path = DATA_PATH) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("stadiums"), list):
        raise VenueIngestError(f"{path.name}: expected an object with a `stadiums` list")
    return data


def _compact(text: str) -> str:
    return "".join(ch for ch in text.upper() if ch.isalnum())


def similarity(a: str, b: str) -> float:
    """Whole-name comparison, deliberately WITHOUT branch-suffix stripping: a shop named after the
    stadium ("<shop> <stadium>점") must not be mistaken for the stadium itself."""
    ca, cb = _compact(a), _compact(b)
    if not ca or not cb:
        return 0.0
    return 1.0 if ca == cb else SequenceMatcher(None, ca, cb).ratio()


def pick_existing(
    entry: Mapping[str, Any],
    candidates: Iterable[ExistingPlace],
    *,
    radius_m: float,
    min_similarity: float,
) -> ExistingPlace | None:
    names = [str(entry["name"]), *[str(a) for a in entry.get("aliases", [])]]
    lat, lng = float(entry["lat"]), float(entry["lng"])
    best: tuple[float, ExistingPlace] | None = None
    for cand in candidates:
        if distance_m(lat, lng, cand.lat, cand.lng) > radius_m:
            continue
        score = max(similarity(name, cand.name) for name in names)
        if score >= min_similarity and (best is None or score > best[0]):
            best = (score, cand)
    return best[1] if best else None


def build_place(entry: Mapping[str, Any], spec: Mapping[str, Any], prior: PricePrior | None) -> BulkPlace:
    category = str(spec["category"])
    schedule_url = str(entry.get("schedule_url") or spec["schedule_url"])
    clubs = [str(c) for c in entry.get("clubs", [])]
    sido = entry.get("sido")
    price = prior.estimate(category, sido, None, str(entry["name"])) if prior else None
    description = str(spec.get("description_template", "")).format(
        clubs=" · ".join(clubs), schedule_url=schedule_url
    )
    return BulkPlace(
        provider=str(spec["provider"]),
        external_id=str(entry["id"]),
        name=str(entry["name"]),
        category_code=category,
        lat=float(entry["lat"]),
        lng=float(entry["lng"]),
        sido=sido,
        sigungu=entry.get("sigungu"),
        address=entry.get("road_address"),
        road_address=entry.get("road_address"),
        description=description or None,
        price_per_person=price,
        price_is_estimated=price is not None,
        raw={
            "clubs": clubs,
            "schedule_url": schedule_url,
            "game_day_only": True,
            "game_day_notice": spec.get("game_day_notice"),
            "coord_source": entry.get("coord_source"),
            "osm": entry.get("osm"),
            "attribution": spec.get("_attribution"),
            "sido": sido,
        },
    )


async def _nearby(
    session: AsyncSession, place: BulkPlace, radius_m: float, roles: Sequence[str], provider: str
) -> list[ExistingPlace]:
    """Approved places around the stadium that are not our own inserts (so a re-run is stable)."""
    d_lat = radius_m * DEG_PER_M
    d_lng = d_lat * 1.4
    own = select(PlaceSource.place_id).where(
        PlaceSource.provider == provider, PlaceSource.match_confidence >= 1.0
    )
    rows = await session.execute(
        select(Place.id, Place.name, Place.lat, Place.lng, Place.phone)
        .join(Category, Category.id == Place.category_id)
        .where(
            Place.lat.between(place.lat - d_lat, place.lat + d_lat),
            Place.lng.between(place.lng - d_lng, place.lng + d_lng),
            Place.status == "approved",
            Category.course_role.in_(roles),
            Place.id.not_in(own),
        )
    )
    return [ExistingPlace(pid, name, lat, lng, phone) for pid, name, lat, lng, phone in rows]


async def _promote(session: AsyncSession, merged: Sequence[BulkPlace]) -> None:
    """The writer's merge path only enriches (phone / photo / measured price). A stadium found in the
    nationwide data must also BECOME a stadium: category, the game-day description and — unless a
    measured price exists — the ticket prior."""
    for p in merged:
        assert p.merge_into_place_id is not None
        category_id = await session.scalar(select(Category.id).where(Category.code == p.category_code))
        values: dict[str, Any] = {"category_id": category_id, "description": p.description}
        measured = await session.scalar(
            select(Place.id).where(
                Place.id == p.merge_into_place_id,
                Place.price_per_person.is_not(None),
                Place.price_is_estimated.is_(False),
            )
        )
        if measured is None and p.price_per_person is not None:
            values.update(
                price_per_person=p.price_per_person,
                price_is_estimated=True,
                price_tier=price_tier(p.price_per_person, False),
                is_free=False,
            )
        await session.execute(update(Place).where(Place.id == p.merge_into_place_id).values(**values))
    await session.commit()


async def load_stadiums(db: Database, *, path: Path = DATA_PATH, log: Log = print) -> BulkReport:
    spec = load_spec(path)
    regions_spec = load_json("regions_kr.json")
    prior = PricePrior.from_data(load_json("price_prior.json"), regions_spec)
    merge = spec.get("merge", {})
    radius_m = float(merge.get("radius_m", 200))
    min_similarity = float(merge.get("min_similarity", 0.8))
    roles = [str(r) for r in merge.get("roles", ["ACTIVITY", "ATTRACTION", "CULTURE"])]
    provider = str(spec["provider"])
    async with db.sessionmaker() as session:
        writer = BulkWriter(session, provider, await RegionIndex.load(session, regions_spec))
        await writer.prepare()
        if not writer.has_category(str(spec["category"])):
            raise VenueIngestError(f"category {spec['category']} is missing — run `seed-config` first")
        places: list[BulkPlace] = []
        for entry in spec["stadiums"]:
            writer.report.read += 1
            place = build_place(entry, spec, prior)
            match = pick_existing(
                entry,
                await _nearby(session, place, radius_m, roles, provider),
                radius_m=radius_m,
                min_similarity=min_similarity,
            )
            if match is not None:
                place.merge_into_place_id = match.id
                log(f"merge  {place.name} -> existing place {match.id} ({match.name})")
            else:
                log(f"own    {place.name} [{entry.get('coord_source')}]")
            writer.report.mapped += 1
            places.append(place)
        await writer.write_all(places)
        await _promote(session, [p for p in places if p.merge_into_place_id is not None])
    return writer.report


async def _main() -> None:
    db = Database(get_settings())
    try:
        for attempt in range(1, LOCK_RETRIES + 1):
            try:
                report = await load_stadiums(db)
                print(report.line())
                return
            except OperationalError as exc:
                if "locked" not in str(exc).lower() or attempt == LOCK_RETRIES:
                    raise
                print(f"database is locked — retry {attempt}/{LOCK_RETRIES} in {LOCK_WAIT_S:.0f}s")
                await asyncio.sleep(LOCK_WAIT_S)
    finally:
        await db.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
