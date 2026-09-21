"""동 · 읍 · 면 as regions (level 4): the unit people actually name when they say where they are going.

A district (시군구) is 3-6 km wide; nobody plans an evening "in a district". The names are not written
anywhere in code or data: they are read from the addresses of the places themselves, and a 동 becomes
a region only when enough places stand in it to plan a course. Its centre is the median of those places,
its radius a distance percentile (rules: `data/bulk/dong_rules.json`).

Places keep their district / hotspot (`place.region_id` is used with `==` all over the code base): a 동
is a circle drawn over its district, and its place count lives in `region_stat`.

Run from apps/api (re-runnable; a 동 that fell under the threshold is set to `paused`):
    uv run python -m app.infra.ingestion.bulk.dongs
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import statistics
import sys
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.core.config import get_settings
from app.domain.models import GeoPoint
from app.domain.routing.travel_time import haversine_m
from app.infra.db.models import Place, Region, RegionStat
from app.infra.db.session import Database
from app.infra.ingestion.bulk.common import load_json

Log = Callable[[str], None]
RULES_FILE = "dong_rules.json"
_BRACKETS = re.compile(r"\(([^)]*)\)")
_HANGUL_NAME = re.compile(r"^[\uac00-\ud7a3][\uac00-\ud7a3\d·]*$")
LOCK_RETRIES = 8
LOCK_WAIT_S = 5.0


@dataclass(slots=True)
class DongReport:
    places: int = 0
    named: int = 0
    dongs: int = 0
    created: int = 0
    updated: int = 0
    paused: int = 0

    def line(self) -> str:
        return (
            f"places={self.places} with_a_dong={self.named} dongs={self.dongs} "
            f"created={self.created} updated={self.updated} paused={self.paused}"
        )


def dong_of(address: str | None, rules: Mapping[str, Any]) -> str | None:
    """The 동 / 읍 / 면 an address names, or None. Works on both address styles:
    "<시도> <시군구> <동> 12-3" and "<시도> <시군구> <road> 12 (<동>)"."""
    if not address:
        return None
    units: Sequence[str] = rules["unit_suffixes"]
    skip: Sequence[str] = rules["skip_suffixes"]
    inside = [t for group in _BRACKETS.findall(address) for t in re.split(r"[ ,]+", group)]
    plain = re.split(r"[ ,]+", _BRACKETS.sub(" ", address))
    numbered = next((i for i, t in enumerate(plain) if t[:1].isdigit()), len(plain))
    plain = plain[:numbered]  # what follows the lot number is a building, not a neighbourhood
    seen_unit = False
    for token in [*plain, *inside]:
        if not _HANGUL_NAME.match(token) or len(token) < 2:
            continue
        if not seen_unit and any(token.endswith(s) for s in skip) and token in plain[:4]:
            continue  # the province / city / district in front
        if any(token.endswith(s) for s in units):
            seen_unit = True
            name = token
            for pattern, to in rules.get("normalize", []):
                name = re.sub(str(pattern), str(to), name)
            return name
    return None


def circle(points: Sequence[GeoPoint], spec: Mapping[str, Any]) -> tuple[GeoPoint, int]:
    centre = GeoPoint(statistics.median(p.lat for p in points), statistics.median(p.lng for p in points))
    reach = sorted(haversine_m(centre, p) for p in points)
    at = reach[min(len(reach) - 1, int(len(reach) * float(spec["percentile"])))]
    return centre, int(max(float(spec["min_m"]), min(float(spec["max_m"]), at)))


def slug_for(district_slug: str, name: str) -> str:
    return f"{district_slug}-d{hashlib.sha1(name.encode('utf-8')).hexdigest()[:6]}"


async def build(db: Database, *, log: Log = print) -> DongReport:
    rules = load_json(RULES_FILE)
    level = int(rules["level"])
    report = DongReport()
    async with db.sessionmaker() as session:
        regions = list((await session.scalars(select(Region))).all())
        by_id = {r.id: r for r in regions}

        def district_of(region_id: int | None) -> Region | None:
            node = by_id.get(region_id or -1)
            while node is not None and node.level > 2:
                node = by_id.get(node.parent_id or -1)
            return node if node is not None and node.level == 2 else None

        groups: dict[tuple[int, str], list[GeoPoint]] = defaultdict(list)
        rows = await session.stream(
            select(Place.region_id, Place.address, Place.road_address, Place.lat, Place.lng).where(
                Place.status == "approved"
            )
        )
        async for region_id, address, road_address, lat, lng in rows:
            report.places += 1
            district = district_of(region_id)
            name = dong_of(address, rules) or dong_of(road_address, rules)
            if district is None or name is None or name == district.name:
                continue
            if district.name not in f"{address or ''} {road_address or ''}":
                continue  # a hotspot reaches over the border: that 동 belongs to the district next door
            report.named += 1
            groups[(district.id, name)].append(GeoPoint(lat, lng))

        existing = {r.slug: r for r in regions if r.level == level}
        stats = {s.region_id: s for s in (await session.scalars(select(RegionStat))).all()}
        kept: set[str] = set()
        for (district_id, name), points in sorted(groups.items()):
            if len(points) < int(rules["min_places"]):
                continue
            district = by_id[district_id]
            slug = slug_for(district.slug, name)
            kept.add(slug)
            centre, radius = circle(points, rules["radius"])
            region = existing.get(slug)
            if region is None:
                region = Region(
                    parent_id=district.id, slug=slug, name=name, level=level,
                    center_lat=centre.lat, center_lng=centre.lng, radius_m=radius,
                    status="active", search_keywords=[district.name],
                )  # fmt: skip
                session.add(region)
                await session.flush()
                report.created += 1
            else:
                region.center_lat, region.center_lng, region.radius_m = centre.lat, centre.lng, radius
                region.status = "active"
                report.updated += 1
            stat = stats.get(region.id)
            if stat is None:
                session.add(RegionStat(region_id=region.id, place_count=len(points)))
            else:
                stat.place_count = len(points)
        for slug, region in existing.items():
            if slug not in kept and region.status == "active":
                region.status = "paused"
                report.paused += 1
        report.dongs = len(kept)
        await session.commit()
    log(report.line())
    return report


async def _main() -> None:
    db = Database(get_settings())
    try:
        await db.create_all()  # `region_stat` on a database made before it existed (SQLite)
        for attempt in range(1, LOCK_RETRIES + 1):
            try:
                await build(db)
                return
            except OperationalError as exc:
                if "locked" not in str(exc).lower() or attempt == LOCK_RETRIES:
                    raise
                print(f"database is locked — retry {attempt}/{LOCK_RETRIES} in {LOCK_WAIT_S:.0f}s")
                await asyncio.sleep(LOCK_WAIT_S)
    finally:
        await db.dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
