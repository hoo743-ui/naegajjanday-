"""Builds and serves neighbourhood signatures (`domain.signature`) from the place table.

Build is an offline job (`cli build-signatures`): one bbox read per region, then a single streaming
pass over every shop name to learn how common each candidate word is nationwide. Serving is a
primary-key read.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.models import GeoPoint
from app.domain.region_draws import Draws, draws_for
from app.domain.signature import (
    Sight,
    Signature,
    SignatureRules,
    Specialty,
    compact,
    count_grams,
    get_signature_rules,
    grams,
    leading_grams,
    pick_specialties,
    place_words,
    rank_sights,
    without,
)
from app.infra.db.models import Category, Place, Region, RegionSignature
from app.infra.db.session import Database
from app.infra.tagging import get_tag_rules
from app.services.directions_service import get_transit_index

log = get_logger(__name__)
STREAM_CHUNK = 20_000
M_PER_DEG = 111_000.0


@dataclass(slots=True)
class _Area:
    region: Region
    region_words: set[str]
    shop_names: list[str]
    sights: list[tuple[int, str, bool]]
    toponyms: set[str]
    local: Counter[str]


@dataclass(frozen=True, slots=True)
class BuildReport:
    regions: int
    with_specialties: int
    with_sights: int


async def _read_area(
    session: AsyncSession,
    region: Region,
    roles: dict[int, str],
    rules: SignatureRules,
    ancestors: list[str],
) -> _Area:
    radius = float(min(region.radius_m, rules.max_radius_m))
    center = GeoPoint(region.center_lat, region.center_lng)
    dlat = radius / M_PER_DEG
    dlng = radius / (M_PER_DEG * max(0.2, math.cos(math.radians(center.lat))))
    rows = await session.execute(
        select(
            Place.id, Place.name, Place.category_id, Place.road_address, Place.address, Place.thumbnail_url
        )
        .where(Place.status == "approved")
        .where(Place.lat.between(center.lat - dlat, center.lat + dlat))
        .where(Place.lng.between(center.lng - dlng, center.lng + dlng))
    )
    tag_rules = get_tag_rules()
    unlisted = tag_rules.is_unlisted

    def is_chain(name: str) -> bool:  # a nationwide brand says nothing about this neighbourhood
        flat = compact(name)
        return any(word in flat for word in tag_rules.chain_words)

    shop_names: list[str] = []
    sights: list[tuple[int, str, bool]] = []
    addresses: Counter[str] = Counter()
    for place_id, name, category_id, road, lot, thumb in rows:
        role = roles.get(category_id, "")
        addresses.update(grams(f"{road or ''} {lot or ''}", rules.gram_lengths))
        if role in rules.specialty_roles and not unlisted(name) and not is_chain(name):
            shop_names.append(name)
        elif role in rules.sight_roles:
            sights.append((place_id, name, bool(thumb)))

    # words that name a place rather than a thing: streets and districts (from the addresses), the
    # region and its parent, nearby stations, and the head or tail of a sight's name
    toponyms = {g for g, hits in addresses.items() if hits >= rules.min_toponym_hits}
    region_words = grams(region.name, rules.gram_lengths)
    for ancestor in ancestors:  # the district, the city, the province: every branch in town carries them
        region_words |= grams(ancestor, rules.gram_lengths)
    toponyms |= region_words
    for station in get_transit_index().station_names_near(center, radius * rules.station_radius_factor):
        toponyms |= grams(station, rules.gram_lengths)
    for _, sight_name, _ in sights:
        parts = [compact(part) for part in sight_name.split()]
        # the whole name and its first/last word; a middle word ("<town> <dish> alley") is the dish itself
        for word in {compact(sight_name), *parts[:1], *parts[-1:]}:
            for n in rules.gram_lengths:
                if len(word) >= n:
                    toponyms.update((word[:n], word[-n:]))
    own = place_words([region.name, *ancestors], rules.admin_suffixes)
    local = count_grams((without(name, own) for name in shop_names), rules.gram_lengths)
    return _Area(region, region_words, shop_names, sights, toponyms, local)


async def build_all(db: Database, only: list[str] | None = None) -> BuildReport:
    rules = get_signature_rules()
    async with db.session() as session:
        roles = {cid: role for cid, role in await session.execute(select(Category.id, Category.course_role))}
        stmt = select(Region).where(Region.level.in_(rules.levels), Region.status == "active")
        if only:
            stmt = stmt.where(Region.slug.in_(only))
        regions = list((await session.execute(stmt)).scalars())
        by_id = {r.id: r for r in (await session.execute(select(Region))).scalars()}

        def ancestors(region: Region) -> list[str]:
            names: list[str] = []
            parent_id = region.parent_id
            while parent_id is not None and parent_id in by_id and len(names) < 4:
                names.append(by_id[parent_id].name)
                parent_id = by_id[parent_id].parent_id
            return names

        areas = [await _read_area(session, region, roles, rules, ancestors(region)) for region in regions]

        candidates: set[str] = set()
        for area in areas:
            candidates |= {g for g, hits in area.local.items() if hits >= rules.min_local}
        shop_category_ids = [cid for cid, role in roles.items() if role in rules.specialty_roles]
        national: Counter[str] = Counter()
        national_leading: Counter[str] = Counter()
        national_shops = 0
        stream = await session.stream(
            select(Place.name)
            .where(Place.status == "approved", Place.category_id.in_(shop_category_ids))
            .execution_options(yield_per=STREAM_CHUNK)
        )
        async for (name,) in stream:
            national_shops += 1
            national.update(grams(name, rules.gram_lengths) & candidates)
            national_leading.update(leading_grams(name, rules.gram_lengths) & candidates)

        with_specialties = with_sights = 0
        for area in areas:
            signature = Signature(
                specialties=pick_specialties(
                    area.local,
                    len(area.shop_names),
                    national,
                    national_shops,
                    area.toponyms,
                    rules,
                    national_leading,
                ),
                sights=rank_sights(area.sights, area.shop_names, rules, area.region_words),
                shops=len(area.shop_names),
            )
            with_specialties += bool(signature.specialties)
            with_sights += bool(signature.sights)
            row = await session.get(RegionSignature, area.region.id)
            if row is None:
                session.add(RegionSignature(region_id=area.region.id, payload=signature.to_payload()))
            else:
                row.payload = signature.to_payload()
        log.info("signature.built", regions=len(areas), national_shops=national_shops)
        return BuildReport(len(areas), with_specialties, with_sights)


async def load(session: AsyncSession, region_id: int) -> Signature:
    """The stored signature, without the sign fragments known to be noise, and — for a neighbourhood
    people come to on purpose — led by what they come for (data/regions/draws.json)."""
    rules = get_signature_rules()
    row = await session.get(RegionSignature, region_id)
    signature = Signature.from_payload(row.payload if row else None).without_words(rules.not_specialties)
    region = await session.get(Region, region_id)
    draws = draws_for(region.slug) if region is not None else None
    if region is None or draws is None:
        return signature
    return await curate(session, region, signature, draws, rules)


async def curate(
    session: AsyncSession, region: Region, signature: Signature, draws: Draws, rules: SignatureRules
) -> Signature:
    """Puts the neighbourhood's draws ahead of what the signs say — only those it really has: a dish on
    at least one shop sign here, a sight that a place within reach is called."""
    center = GeoPoint(region.center_lat, region.center_lng)
    radius = float(max(region.radius_m, 800))
    dlat = radius / M_PER_DEG
    dlng = radius / (M_PER_DEG * max(0.2, math.cos(math.radians(center.lat))))
    stmt = (
        select(Place.id, Place.name, Category.course_role)
        .join(Category, Category.id == Place.category_id)
        .where(Place.status == "approved")
        .where(Place.lat.between(center.lat - dlat, center.lat + dlat))
        .where(Place.lng.between(center.lng - dlng, center.lng + dlng))
        .where(Category.course_role.in_(rules.specialty_roles | rules.sight_roles))
    )
    shops: list[str] = []
    sights: list[tuple[int, str]] = []
    for place_id, name, role in (await session.execute(stmt)).all():
        if role in rules.specialty_roles:
            shops.append(compact(name))
        else:
            sights.append((place_id, name))
    eat = [
        Specialty(word, n, 0.0, curated=True)
        for word in draws.eat
        if (n := sum(1 for shop in shops if compact(word) in shop))
    ]
    seen: set[int] = set()
    see: list[Sight] = []
    for needle in draws.see:
        key = compact(needle)
        named = sorted(
            (n for n in sights if key in compact(n[1]) and n[0] not in seen), key=lambda n: len(n[1])
        )
        if named:
            seen.add(named[0][0])
            see.append(Sight(named[0][0], named[0][1], 0, curated=True))
    words = [s for s in signature.specialties if not any(s.word in e.word or e.word in s.word for e in eat)]
    return Signature(
        specialties=tuple([*eat, *words][: max(rules.max_specialties, len(eat))]),
        sights=tuple([*see, *(s for s in signature.sights if s.place_id not in seen)]),
        shops=signature.shops,
    )
