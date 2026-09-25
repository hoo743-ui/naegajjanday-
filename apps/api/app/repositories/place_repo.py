from __future__ import annotations

import math
from collections.abc import Sequence
from copy import copy
from datetime import date, time
from typing import Any

from sqlalchemy import ColumnElement, and_, case, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.anchors import AnchoredEvent, event_window
from app.domain.models import GeoPoint, OpeningPeriod, PlaceCandidate
from app.domain.routing.travel_time import haversine_m
from app.infra.db.base import as_utc
from app.infra.db.models import Category, Event, OpeningHour, Place, PlaceStats, PlaceTag, Region, Tag
from app.infra.default_hours import get_default_hours
from app.infra.tagging import get_tag_rules, merge_tags
from app.repositories.geo import nearest_first, within

EVENT_ROLES = {"ATTRACTION", "CULTURE"}
CURATED_TAG = "관광공사 소개"  # derived by tag_rules.json › listed_by_kto
# A busy district holds thousands of places per role and the engine can weigh a few hundred. Taking
# the nearest N made "within the radius" mean "within 300 m of the centre": whole neighbourhoods and
# nearly every place with a reason to be recommended never reached the scorer. So the pool is built
# from three reads: the places we know something good about, the walkable core, and an even sample
# of everything else in the radius. Distance is then one score among the others, as it should be.
NOTABLE_LIMIT = 200  # a real photo (tourism board), a measured price, or a local-specialty sign
CORE_LIMIT = 400  # nearest first
STANDOUT_LIMIT = 150  # v2 adaptive reach: the far places that might be worth the trip
SPREAD_LIMIT = 150  # spread over the whole radius
SPREAD_MULTIPLIER, SPREAD_MODULUS = 7919, 1009  # a fixed shuffle of ids: same request, same pool
OVEREXPOSED_TOP_RATIO = 0.05
OVEREXPOSED_MIN_POOL = 20


def _minutes(t: time | None) -> int | None:
    return None if t is None else t.hour * 60 + t.minute


def to_opening_period(h: OpeningHour) -> OpeningPeriod | None:
    if h.is_closed:
        return OpeningPeriod(h.dow, 0, 0, is_closed=True)
    open_min, close_min = _minutes(h.open_time), _minutes(h.close_time)
    if open_min is None or close_min is None:
        return None
    if close_min <= open_min:  # past midnight ("00:00"-"00:00" = 24h)
        close_min += 1440
    return OpeningPeriod(h.dow, open_min, close_min, _minutes(h.break_start), _minutes(h.break_end))


def to_candidate(place: Place) -> PlaceCandidate:
    """Requires category, stats, opening_hours, popular_times and place_tags to be eagerly loaded."""
    stats, cat = place.stats, place.category
    derived = get_tag_rules().derive(
        category_code=cat.code,
        name=place.name,
        course_role=cat.course_role,
        has_measured_price=place.price_per_person is not None
        and not place.price_is_estimated
        and not place.is_free,
        photo_url=place.thumbnail_url,
    )
    tags = merge_tags({pt.tag.name: pt.weight for pt in place.place_tags}, derived)
    vouched = get_tag_rules().quality_tags or frozenset({CURATED_TAG})
    return PlaceCandidate(
        id=place.id,
        public_id=place.public_id,
        name=get_tag_rules().sign_name(place.name),
        category_code=cat.code,
        category_name=cat.name,
        # no reviews exist: "an official body vouches for it" is the quality signal we do have
        is_curated=any(tag in vouched for tag in tags),
        course_role=cat.course_role,
        lat=place.lat,
        lng=place.lng,
        price_per_person=place.price_per_person,
        price_is_estimated=bool(place.price_is_estimated) and not place.is_free,
        is_free=place.is_free,
        address=place.road_address or place.address,
        thumbnail_url=place.thumbnail_url,
        default_stay_min=cat.default_stay_min,
        rating_avg=stats.rating_avg if stats else None,
        rating_count=stats.rating_count if stats else 0,
        bayes_rating=stats.bayes_rating if stats else None,
        sentiment_score=stats.sentiment_score if stats else None,
        sentiment_count=stats.sentiment_count if stats else 0,
        aspect_scores=dict(stats.aspect_scores or {}) if stats else {},
        popularity=stats.popularity if stats else 0.0,
        tags=tags,
        # no hours of its own (99 % of bulk data) → the category's usual hours, so nobody is sent to a
        # museum at 20:30; real hours always win
        opening_hours=[p for h in place.opening_hours if (p := to_opening_period(h)) is not None]
        or list(get_default_hours().for_place(cat.code, place.name, place.road_address or place.address)),
        popular_times={(pt.dow, pt.hour): pt.congestion for pt in place.popular_times},
        approved_at=as_utc(place.approved_at),
    )


# what an event with no category is taken for (event_to_candidate) and what counts as a campus festival
FESTIVAL_CATEGORY = "culture.festival"


def event_hours(event: Event) -> list[OpeningPeriod]:
    """An event with hours (docs/34) is "open" only then, every day of its run — so the engine's own
    open check keeps the meal before and the walk there inside the day. Without hours: the date alone."""
    window = event_window(event.start_time, event.end_time)
    if window is None:
        return []
    return [OpeningPeriod(dow=dow, open_min=window[0], close_min=window[1]) for dow in range(7)]


def event_to_candidate(event: Event) -> PlaceCandidate:
    cat = event.category
    return PlaceCandidate(
        id=event.id,
        public_id=event.public_id,
        name=event.title,
        category_code=cat.code if cat else FESTIVAL_CATEGORY,
        category_name=cat.name if cat else "축제",
        course_role=cat.course_role if cat else "CULTURE",
        lat=event.lat,
        lng=event.lng,
        price_per_person=event.price,
        is_free=event.is_free,
        address=event.address,
        thumbnail_url=(event.images or [None])[0],
        default_stay_min=cat.default_stay_min if cat else 60,
        opening_hours=event_hours(event),
        is_event=True,
    )


FULL_LOAD = (
    selectinload(Place.category),
    selectinload(Place.stats),
    selectinload(Place.opening_hours),
    selectinload(Place.popular_times),
    selectinload(Place.place_tags),
)


class SqlPlaceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session
        self._dialect = session.get_bind().dialect.name

    # --- CandidateSource (domain Protocol) ---------------------------------------------------

    async def fetch(
        self, role: str, origin: GeoPoint, radius_m: float, on_date: date, name_words: Sequence[str] = ()
    ) -> list[PlaceCandidate]:
        rules = get_tag_rules()
        # the three reads pick rows by id only; the chosen places are then loaded once, with everything
        # the engine needs (the reads overlap, and each eager load was a handful of queries of its own)
        base = (
            select(Place.id, Place.lat, Place.lng, Place.name, PlaceStats.recommend_count)
            .join(Category, Category.id == Place.category_id)
            .outerjoin(PlaceStats, PlaceStats.place_id == Place.id)
            .where(Place.status == "approved", Category.course_role == role)
            .where(within(Place, origin, radius_m, self._dialect))
        )
        near = nearest_first(Place, origin)
        vouched = select(PlaceTag.place_id).join(Tag, Tag.id == PlaceTag.tag_id)
        notable = or_(
            Place.thumbnail_url.is_not(None),
            Place.price_is_estimated.is_(False),
            Place.id.in_(vouched.where(Tag.name.in_(sorted(rules.quality_tags)))),
            *(Place.name.contains(word) for word in name_words),
        )
        shuffled = (Place.id * SPREAD_MULTIPLIER) % SPREAD_MODULUS
        reads = (
            base.where(notable).order_by(near, Place.id).limit(NOTABLE_LIMIT),
            base.order_by(near, Place.id).limit(CORE_LIMIT),
            base.order_by(shuffled, Place.id).limit(SPREAD_LIMIT),
        )
        picked: dict[int, int] = {}  # place id → recommend count, in the order the reads found them
        for stmt in reads:
            for place_id, lat, lng, name, recommend_count in (await self._s.execute(stmt)).all():
                if place_id in picked or haversine_m(origin, GeoPoint(lat, lng)) > radius_m:
                    continue
                if rules.is_unlisted(name):  # a company name, not a sign anyone can find
                    continue
                picked[place_id] = recommend_count or 0
        loaded = (
            {
                p.id: p
                for p in (
                    await self._s.scalars(select(Place).where(Place.id.in_(list(picked))).options(*FULL_LOAD))
                ).all()
            }
            if picked
            else {}
        )
        out: list[PlaceCandidate] = []
        exposure: list[tuple[int, PlaceCandidate]] = []
        for place_id, recommend_count in picked.items():
            cand = to_candidate(loaded[place_id])
            out.append(cand)
            exposure.append((recommend_count, cand))
        if len(exposure) >= OVEREXPOSED_MIN_POOL:  # exploration: damp the most-exposed 5 %
            exposure.sort(key=lambda t: -t[0])
            for count, cand in exposure[: max(1, int(len(exposure) * OVEREXPOSED_TOP_RATIO))]:
                cand.is_overexposed = count > 0
        if role in EVENT_ROLES:
            for event, _dist in await self.events_near(origin, radius_m, on_date):
                cand = event_to_candidate(event)
                if cand.course_role == role:
                    out.append(cand)
        return out

    async def fetch_standouts(
        self,
        role: str,
        origin: GeoPoint,
        radius_m: float,
        *,
        min_popularity: float,
        name_words: Sequence[str] = (),
        place_ids: Sequence[int] = (),
    ) -> list[PlaceCandidate]:
        """Only the places worth going further for (docs/29 adaptive reach): measurably visited, vouched for
        by a public body (a quality tag, or a tourism-board listing — they carry its photo), a landmark of
        the area, or a sign with the area's specialty. Loading every shop within 3 km to keep four was the
        slowest part of a v2 request."""
        rules = get_tag_rules()
        vouched = select(PlaceTag.place_id).join(Tag, Tag.id == PlaceTag.tag_id)
        standout = or_(
            PlaceStats.popularity >= min_popularity,
            Place.thumbnail_url.is_not(None),
            Place.id.in_(vouched.where(Tag.name.in_(sorted(rules.quality_tags)))),
            Place.id.in_(list(place_ids)) if place_ids else Place.id.is_(None),
            *(Place.name.contains(word) for word in name_words),
        )
        stmt = (
            select(Place)
            .join(Category, Category.id == Place.category_id)
            .outerjoin(PlaceStats, PlaceStats.place_id == Place.id)
            .where(Place.status == "approved", Category.course_role == role, standout)
            .where(within(Place, origin, radius_m, self._dialect))
            .options(*FULL_LOAD)
            .order_by(PlaceStats.popularity.desc().nulls_last(), Place.id)
            .limit(STANDOUT_LIMIT)
        )
        out = []
        for place in (await self._s.scalars(stmt)).all():
            if haversine_m(origin, GeoPoint(place.lat, place.lng)) > radius_m or rules.is_unlisted(
                place.name
            ):
                continue
            out.append(to_candidate(place))
        return out

    async def events_near(
        self, origin: GeoPoint, radius_m: float, on_date: date
    ) -> list[tuple[Event, float]]:
        stmt = (
            select(Event)
            .where(Event.status == "approved", Event.starts_on <= on_date, Event.ends_on >= on_date)
            .where(within(Event, origin, radius_m, self._dialect))
            .options(selectinload(Event.category))
            .limit(100)
        )
        found = []
        for event in (await self._s.scalars(stmt)).all():
            dist = haversine_m(origin, GeoPoint(event.lat, event.lng))
            if dist <= radius_m:
                found.append((event, dist))
        return sorted(found, key=lambda t: t[1])

    async def campus(self, public_id: str, category: str) -> Place | None:
        """An approved campus place (docs/34) by its public id."""
        stmt = (
            select(Place)
            .join(Category, Category.id == Place.category_id)
            .where(Place.public_id == public_id, Place.status == "approved", Category.code == category)
        )
        return await self._s.scalar(stmt)

    async def search_campuses(
        self, q: str | None, category: str, limit: int = 20, also: str | None = None
    ) -> list[Place]:
        """Campuses by name — "가천"; `also` is the school a nickname stands for ("외대" → 한국외국어대학교),
        in name order."""
        stmt = (
            select(Place)
            .join(Category, Category.id == Place.category_id)
            .where(Place.status == "approved", Category.code == category)
        )
        if q:
            match = Place.name.contains(q.strip())
            stmt = stmt.where(or_(match, Place.name.contains(also)) if also else match)
            if also:  # the school the nickname means before others that merely contain it ("성대" · 경성대)
                stmt = stmt.order_by(case((Place.name.contains(also), 0), else_=1))
        stmt = stmt.order_by(func.length(Place.name), Place.name).limit(limit)
        return list((await self._s.scalars(stmt)).all())

    async def anchored_events(
        self, place_id: int, origin: GeoPoint, radius_m: float, on_date: date
    ) -> list[AnchoredEvent]:
        """That day's events of this campus: linked to it (an admin-entered university festival) or a
        public *festival* held within the campus ring. An exhibition or a performance next door is not the
        campus's festival — it still shows up among the nearby events of the result page."""
        festival = or_(Event.category_id.is_(None), Category.code == FESTIVAL_CATEGORY)
        stmt = (
            select(Event)
            .outerjoin(Category, Category.id == Event.category_id)
            .where(Event.status == "approved", Event.starts_on <= on_date, Event.ends_on >= on_date)
            .where(
                or_(
                    Event.anchor_place_id == place_id,
                    and_(festival, within(Event, origin, radius_m, self._dialect)),
                )
            )
            .limit(50)
        )
        out = []
        for event in (await self._s.scalars(stmt)).all():
            dist = haversine_m(origin, GeoPoint(event.lat, event.lng))
            anchored = event.anchor_place_id == place_id
            if not anchored and dist > radius_m:
                continue
            out.append(
                AnchoredEvent(
                    id=event.id,
                    title=event.title,
                    starts_on=event.starts_on,
                    ends_on=event.ends_on,
                    start_time=event.start_time,
                    end_time=event.end_time,
                    priority=event.priority or 0,
                    anchored=anchored,
                    distance_m=dist,
                )
            )
        return out

    async def candidates_by_ids(self, place_ids: Sequence[int]) -> dict[int, PlaceCandidate]:
        if not place_ids:
            return {}
        stmt = select(Place).where(Place.id.in_(place_ids)).options(*FULL_LOAD)
        return {p.id: to_candidate(p) for p in (await self._s.scalars(stmt)).all()}

    async def event_candidates_by_ids(self, event_ids: Sequence[int]) -> dict[int, PlaceCandidate]:
        if not event_ids:
            return {}
        stmt = select(Event).where(Event.id.in_(event_ids)).options(selectinload(Event.category))
        return {e.id: event_to_candidate(e) for e in (await self._s.scalars(stmt)).all()}

    async def candidates_by_public_ids(self, public_ids: Sequence[str]) -> dict[str, PlaceCandidate]:
        """Approved places and events by their public id (a stop can be either), keyed by that id."""
        if not public_ids:
            return {}
        ids = list(public_ids)
        places = await self._s.scalars(
            select(Place).where(Place.public_id.in_(ids), Place.status == "approved").options(*FULL_LOAD)
        )
        out = {p.public_id: to_candidate(p) for p in places.all()}
        missing = [i for i in ids if i not in out]
        if missing:
            events = await self._s.scalars(
                select(Event).where(Event.public_id.in_(missing)).options(selectinload(Event.category))
            )
            out.update({e.public_id: event_to_candidate(e) for e in events.all()})
        return out

    async def category_rating_avg(self, region_id: int | None) -> dict[str, float]:
        stmt = (
            select(
                Category.code,
                func.sum(PlaceStats.rating_avg * PlaceStats.rating_count),
                func.sum(PlaceStats.rating_count),
            )
            .join(Place, Place.category_id == Category.id)
            .join(PlaceStats, PlaceStats.place_id == Place.id)
            .where(PlaceStats.rating_count > 0, PlaceStats.rating_avg.is_not(None))
            .group_by(Category.code)
        )
        if region_id is not None:
            stmt = stmt.where(Place.region_id == region_id)
        return {code: total / n for code, total, n in (await self._s.execute(stmt)).all() if n}

    async def bump_recommend_count(self, place_ids: Sequence[int]) -> None:
        if place_ids:
            await self._s.execute(
                update(PlaceStats)
                .where(PlaceStats.place_id.in_(place_ids))
                .values(recommend_count=PlaceStats.recommend_count + 1)
            )

    # --- read side ---------------------------------------------------------------------------

    async def hot_places(
        self,
        region_ids: Sequence[int],
        roles: Sequence[str],
        limit: int,
        *,
        around: tuple[GeoPoint, float] | None = None,
    ) -> list[Place]:
        """The most visited places of these regions, most visited first (category and stats loaded).
        `around` (centre, metres) keeps those inside a box: a 동 owns no places, it is drawn over them."""
        inside = []
        if around is not None:
            centre, reach_m = around
            d_lat = reach_m / 111_000
            d_lng = reach_m / (111_000 * max(0.2, math.cos(math.radians(centre.lat))))
            inside = [
                Place.lat.between(centre.lat - d_lat, centre.lat + d_lat),
                Place.lng.between(centre.lng - d_lng, centre.lng + d_lng),
            ]
        rows = await self._s.scalars(
            select(Place)
            .join(PlaceStats, PlaceStats.place_id == Place.id)
            .join(Category, Category.id == Place.category_id)
            .where(
                *inside,
                Place.region_id.in_(list(region_ids)),
                Place.status == "approved",
                PlaceStats.popularity > 0,
                Category.course_role.in_(list(roles)),
            )
            .options(selectinload(Place.category), selectinload(Place.stats))
            .order_by(PlaceStats.popularity.desc(), Place.thumbnail_url.is_(None), Place.id)
            .limit(limit)
        )
        return list(rows.all())

    async def popular_sights(
        self, region_ids: Sequence[int], roles: Sequence[str], min_popularity: float, limit: int
    ) -> list[tuple[int, str, GeoPoint, float, str]]:
        """(id, name, point, popularity, category code) of the most visited sights in these regions — measured
        navigation ranks, see `ingestion.bulk.visit_hubs`."""
        rows = await self._s.execute(
            select(Place.id, Place.name, Place.lat, Place.lng, PlaceStats.popularity, Category.code)
            .join(PlaceStats, PlaceStats.place_id == Place.id)
            .join(Category, Category.id == Place.category_id)
            .where(
                Place.region_id.in_(list(region_ids)),
                Place.status == "approved",
                PlaceStats.popularity >= min_popularity,
                Category.course_role.in_(list(roles)),
            )
            .order_by(PlaceStats.popularity.desc(), Place.id)
            .limit(limit)
        )
        return [(pid, name, GeoPoint(lat, lng), float(pop), code) for pid, name, lat, lng, pop, code in rows]

    async def get_by_public_id(self, public_id: str) -> Place | None:
        stmt = (
            select(Place)
            .where(Place.public_id == public_id)
            .options(
                *FULL_LOAD,
                selectinload(Place.menu_items),
                selectinload(Place.region),
                selectinload(Place.sources),  # the licence record: opening year, kind of business
            )
        )
        return await self._s.scalar(stmt)

    async def ids_by_public_ids(self, public_ids: Sequence[str]) -> set[int]:
        if not public_ids:
            return set()
        return set((await self._s.scalars(select(Place.id).where(Place.public_id.in_(public_ids)))).all())

    async def search_sql(
        self,
        *,
        q: str | None,
        region_slug: str | None,
        roles: Sequence[str] | None,
        max_price: int | None,
        origin: GeoPoint | None,
        radius_m: float | None,
        sort: str,
        limit: int,
        offset: int = 0,
        prefix: bool = False,
    ) -> list[tuple[PlaceCandidate, float | None]]:
        """Fallback for Elasticsearch: LIKE search on the canonical tables."""
        stmt = (
            select(Place)
            .join(Category, Category.id == Place.category_id)
            .outerjoin(PlaceStats, PlaceStats.place_id == Place.id)
            .where(Place.status == "approved")
            .options(*FULL_LOAD)
        )
        if q:
            like = f"{_escape_like(q)}%" if prefix else f"%{_escape_like(q)}%"
            match: Any = Place.name.ilike(like, escape="\\")
            if not prefix:
                match = or_(
                    match, Place.address.ilike(like, escape="\\"), Category.name.ilike(like, escape="\\")
                )
            stmt = stmt.where(match)
        if region_slug:
            stmt = stmt.join(Region, Region.id == Place.region_id).where(Region.slug == region_slug)
        if roles:
            stmt = stmt.where(Category.course_role.in_(roles))
        if max_price is not None:
            stmt = stmt.where(or_(Place.is_free.is_(True), Place.price_per_person <= max_price))
        if origin is not None and radius_m:
            stmt = stmt.where(within(Place, origin, radius_m, self._dialect))
        orders: dict[str, ColumnElement[Any]] = {
            "rating": PlaceStats.bayes_rating.desc().nulls_last(),
            "price": Place.price_per_person.asc().nulls_first(),
            "popularity": PlaceStats.popularity.desc().nulls_last(),
        }
        order = orders.get(sort, orders["rating"])
        fetch_n = limit * 4 if origin is not None else limit
        rows = (await self._s.scalars(stmt.order_by(order, Place.id).offset(offset).limit(fetch_n))).all()
        out: list[tuple[PlaceCandidate, float | None]] = []
        for place in rows:
            dist = haversine_m(origin, GeoPoint(place.lat, place.lng)) if origin is not None else None
            if dist is not None and radius_m and dist > radius_m:
                continue
            out.append((to_candidate(place), dist))
        if sort == "distance" and origin is not None:
            out.sort(key=lambda t: t[1] or 0.0)
        return out[:limit]

    async def place_tags(self, place_id: int) -> list[PlaceTag]:
        return list((await self._s.scalars(select(PlaceTag).where(PlaceTag.place_id == place_id))).all())


class CandidateReads:
    """The candidate reads of one plan, each done once (docs/29 "남은 것" · latency).

    Planning one request asks the same questions many times: every rescale pass and the v2 structure
    alternative re-collect the pools, and each day of a trip around the same neighbourhood asks again.
    Loading and converting the rows was most of a request. A plan's reads are remembered here, keyed on
    everything that shapes the answer; the date only where it matters (events on ATTRACTION/CULTURE).

    Every call hands out copies: the engine marks candidates per pass (buzz, local_score, local_word), and
    a copy keeps each pass exactly as it was when every read was fresh. Live only for one plan: nothing is
    written in between, so the answers cannot go stale."""

    def __init__(self, repo: SqlPlaceRepository) -> None:
        self._repo = repo
        self._seen: dict[tuple[Any, ...], list[PlaceCandidate]] = {}

    async def fetch(
        self, role: str, origin: GeoPoint, radius_m: float, on_date: date, name_words: Sequence[str] = ()
    ) -> list[PlaceCandidate]:
        day = on_date if role in EVENT_ROLES else None
        key = ("fetch", role, origin, radius_m, day, tuple(name_words))
        found = self._seen.get(key)
        if found is None:
            found = self._seen[key] = await self._repo.fetch(role, origin, radius_m, on_date, name_words)
        return [copy(c) for c in found]

    async def fetch_standouts(
        self,
        role: str,
        origin: GeoPoint,
        radius_m: float,
        *,
        min_popularity: float,
        name_words: Sequence[str] = (),
        place_ids: Sequence[int] = (),
    ) -> list[PlaceCandidate]:
        key = ("standouts", role, origin, radius_m, min_popularity, tuple(name_words), tuple(place_ids))
        found = self._seen.get(key)
        if found is None:
            found = self._seen[key] = await self._repo.fetch_standouts(
                role,
                origin,
                radius_m,
                min_popularity=min_popularity,
                name_words=name_words,
                place_ids=place_ids,
            )
        return [copy(c) for c in found]


def _escape_like(q: str) -> str:
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
