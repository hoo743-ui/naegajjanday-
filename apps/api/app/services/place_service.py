from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core import errors
from app.core.config import Settings
from app.core.logging import get_logger
from app.domain.models import GeoPoint, PlaceCandidate
from app.infra.db.base import utcnow
from app.infra.db.models import (
    Category,
    Event,
    Place,
    PlaceRevision,
    PlaceSource,
    PlaceStats,
    Region,
    User,
)
from app.infra.search.client import PlaceSearch, SearchQuery
from app.infra.tagging import get_tag_rules
from app.repositories.place_repo import SqlPlaceRepository
from app.repositories.region_repo import SqlRegionRepository
from app.schemas import place as dto
from app.services.course_service import place_brief

# the licence registry rows attached by `ingest-bulk marks` (keys are the registry's own column names)
LICENCE_PROVIDERS = ("lic_restaurant", "lic_cafe")
LICENCE_DATE_KEY = "\uc778\ud5c8\uac00\uc77c\uc790"
LICENCE_KIND_KEY = "\uc5c5\ud0dc\uad6c\ubd84\uba85"

logger = get_logger(__name__)

ATTRACTION_TYPES: dict[str, tuple[str, ...]] = {
    # API `type` filter → category code prefixes (categories themselves are data)
    "park": ("attraction.park",),
    "exhibition": ("culture.exhibition", "culture.gallery", "culture.museum"),
    "festival": ("culture.festival",),
    "culture": ("culture",),
    "attraction": ("attraction", "nightview"),
}


def _fmt(t: time | None) -> str | None:
    return t.strftime("%H:%M") if t else None


class PlaceService:
    def __init__(self, settings: Settings, session: AsyncSession, search: PlaceSearch | None) -> None:
        self._settings = settings
        self._s = session
        self._search = search
        self._places = SqlPlaceRepository(session)
        self._regions = SqlRegionRepository(session)
        self._tz = ZoneInfo(settings.timezone)

    @staticmethod
    def _item(c: PlaceCandidate, dist: float | None) -> dto.PlaceSearchItem:
        return dto.PlaceSearchItem(
            **place_brief(c).model_dump(),
            role=c.course_role,
            distance_m=round(dist) if dist is not None else None,
        )

    async def search(
        self,
        *,
        q: str | None,
        region: str | None,
        role: str | None,
        max_price: int | None,
        lat: float | None,
        lng: float | None,
        radius: float | None,
        sort: str,
        limit: int,
        offset: int,
    ) -> dto.PlaceSearchResponse:
        roles = tuple(r.strip().upper() for r in role.split(",") if r.strip()) if role else ()
        origin = GeoPoint(lat, lng) if lat is not None and lng is not None else None
        if self._search is not None:
            try:
                hits = await self._search.search(
                    SearchQuery(q, region, roles, max_price, lat, lng, radius, sort, limit + 1, offset)
                )
                ids = await self._ids_in_order([h.public_id for h in hits])
                cands = await self._places.candidates_by_ids(list(ids.values()))
                items = [
                    self._item(cands[ids[h.public_id]], h.distance_m)
                    for h in hits
                    if h.public_id in ids and ids[h.public_id] in cands
                ]
                return self._page(items, limit, offset, self._search.backend)
            except Exception as exc:  # ES outage must not take search down
                logger.warning("search.es_failed_fallback_sql", error=str(exc))
        rows = await self._places.search_sql(
            q=q,
            region_slug=region,
            roles=roles,
            max_price=max_price,
            origin=origin,
            radius_m=radius,
            sort=sort,
            limit=limit + 1,
            offset=offset,
        )
        return self._page([self._item(c, d) for c, d in rows], limit, offset, "sql")

    @staticmethod
    def _page(
        items: list[dto.PlaceSearchItem], limit: int, offset: int, engine: str
    ) -> dto.PlaceSearchResponse:
        more = len(items) > limit
        return dto.PlaceSearchResponse(
            items=items[:limit], next_cursor=str(offset + limit) if more else None, engine=engine
        )

    async def _ids_in_order(self, public_ids: list[str]) -> dict[str, int]:
        if not public_ids:
            return {}
        rows = await self._s.execute(select(Place.public_id, Place.id).where(Place.public_id.in_(public_ids)))
        return {pid: i for pid, i in rows.all()}

    async def autocomplete(self, q: str, limit: int = 8) -> dto.AutocompleteResponse:
        cands: list[PlaceCandidate] = []
        if self._search is not None:
            try:
                ids = await self._ids_in_order(await self._search.autocomplete(q, limit))
                found = await self._places.candidates_by_ids(list(ids.values()))
                cands = [found[i] for i in ids.values() if i in found]
            except Exception as exc:
                logger.warning("autocomplete.es_failed_fallback_sql", error=str(exc))
        if not cands:
            rows = await self._places.search_sql(
                q=q,
                region_slug=None,
                roles=None,
                max_price=None,
                origin=None,
                radius_m=None,
                sort="popularity",
                limit=limit,
                prefix=True,
            )
            if not rows:  # "홍대 파" → match the last token
                last = q.split()[-1] if q.split() else q
                rows = await self._places.search_sql(
                    q=last,
                    region_slug=None,
                    roles=None,
                    max_price=None,
                    origin=None,
                    radius_m=None,
                    sort="popularity",
                    limit=limit,
                )
            cands = [c for c, _ in rows]
        return dto.AutocompleteResponse(
            items=[dto.AutocompleteItem(id=c.public_id, name=c.name, category=c.category_code) for c in cands]
        )

    async def detail(self, public_id: str) -> dto.PlaceDetail:
        place = await self._places.get_by_public_id(public_id)
        if place is None or place.status not in {"approved"}:
            raise errors.PlaceNotFound()
        from app.repositories.place_repo import to_candidate

        cand = to_candidate(place)
        today = datetime.now(self._tz).weekday()
        licence = next((s.raw for s in place.sources if s.provider in LICENCE_PROVIDERS and s.raw), {})
        since = str(licence.get(LICENCE_DATE_KEY) or "")[:4]
        mark_by = get_tag_rules().mark_sources
        stats = place.stats
        return dto.PlaceDetail(
            **place_brief(cand).model_dump(),
            role=cand.course_role,
            region=place.region.slug,
            phone=place.phone,
            description=place.description,
            since_year=int(since)
            if since.isdigit() and 1900 < int(since) <= datetime.now(self._tz).year
            else None,
            licensed_as=(str(licence.get(LICENCE_KIND_KEY)) or None) if licence else None,
            marks=[dto.OfficialMark(tag=t, by=mark_by[t]) for t in cand.tags if t in mark_by],
            images=list(place.images or []),
            menus=[
                dto.MenuOut(name=m.name, price=m.price, is_signature=m.is_signature)
                for m in sorted(place.menu_items, key=lambda m: (not m.is_signature, m.price))
            ],
            opening_hours=[
                dto.OpeningHourOut(
                    dow=h.dow,
                    open=_fmt(h.open_time),
                    close=_fmt(h.close_time),
                    break_start=_fmt(h.break_start),
                    break_end=_fmt(h.break_end),
                    is_closed=h.is_closed,
                )
                for h in sorted(place.opening_hours, key=lambda h: h.dow)
            ],
            congestion_today=[
                dto.CongestionHour(hour=p.hour, value=round(p.congestion, 2))
                for p in sorted(place.popular_times, key=lambda p: p.hour)
                if p.dow == today
            ],
            reviews=dto.ReviewSummary(
                rating=stats.rating_avg if stats else None,
                review_count=stats.rating_count if stats else 0,
                bayes_rating=stats.bayes_rating if stats else None,
                sentiment_score=stats.sentiment_score if stats else None,
                sentiment_count=stats.sentiment_count if stats else 0,
                aspects=dict(stats.aspect_scores or {}) if stats else {},
            ),
        )

    async def nearby(
        self, public_id: str, role: str | None, radius_m: float, limit: int
    ) -> dto.PlaceSearchResponse:
        place = await self._places.get_by_public_id(public_id)
        if place is None:
            raise errors.PlaceNotFound()
        rows = await self._places.search_sql(
            q=None,
            region_slug=None,
            roles=[role.upper()] if role else None,
            max_price=None,
            origin=GeoPoint(place.lat, place.lng),
            radius_m=radius_m,
            sort="distance",
            limit=limit + 1,
        )
        items = [self._item(c, d) for c, d in rows if c.public_id != public_id][:limit]
        return dto.PlaceSearchResponse(items=items, next_cursor=None, engine="sql")

    async def _region(self, slug: str) -> Region:
        region = await self._regions.get_by_slug(slug)
        if region is None:
            raise errors.RegionNotFound(f"'{slug}' 지역은 아직 없어요.")
        return region

    async def events(
        self, region_slug: str | None, date_from: date | None, date_to: date | None
    ) -> dto.EventList:
        region = await self._region(region_slug) if region_slug else None
        start = date_from or datetime.now(self._tz).date()
        end = date_to or start
        stmt = (
            select(Event)
            .where(Event.status == "approved")
            .where(Event.starts_on <= end, Event.ends_on >= start)
            .options(selectinload(Event.category))
            .order_by(Event.ends_on)
            .limit(200)
        )
        if region is not None:
            stmt = stmt.where(Event.region_id == region.id)
        return dto.EventList(items=[_event_out(e) for e in (await self._s.scalars(stmt)).all()])

    async def attractions(
        self, region_slug: str | None, types: str | None, on_date: date | None, q: str | None = None
    ) -> dto.AttractionList:
        region = await self._region(region_slug) if region_slug else None
        wanted = [t.strip() for t in types.split(",") if t.strip()] if types else list(ATTRACTION_TYPES)
        unknown = [t for t in wanted if t not in ATTRACTION_TYPES]
        if unknown:
            raise errors.ValidationFailed(f"type 은 {', '.join(ATTRACTION_TYPES)} 중에서 골라 주세요.")
        prefixes = {t: ATTRACTION_TYPES[t] for t in wanted}

        def type_of(code: str) -> str | None:
            return next(
                (t for t, pre in prefixes.items() if any(code == p or code.startswith(p + ".") for p in pre)),
                None,
            )

        items: list[dto.AttractionItem] = []
        # category ids first: `category_id IN (…) AND status` rides ix_place_category_status_lat_lng and
        # touches only the ~30k sights, where the join made SQLite walk all 800k places (2.2 s → ms)
        sights = await self._s.execute(
            select(Category.id, Category.code).where(
                Category.course_role.in_(["ATTRACTION", "CULTURE", "NIGHTVIEW"])
            )
        )
        # the asked-for types are filtered HERE, before the 300-row cap. Filtering afterwards meant that
        # "parks, everywhere" came back empty: the first 300 sights with a photo were all markets.
        sight_ids = [cid for cid, code in sights if type_of(code) is not None]
        stmt = (
            select(Place)
            .outerjoin(PlaceStats, PlaceStats.place_id == Place.id)
            .where(Place.category_id.in_(sight_ids), Place.status == "approved")
            .options(selectinload(Place.category), selectinload(Place.stats))
            # a card with the place's own photo is worth more than one with a stand-in → those first;
            # then where people really go (measured navigation rank), then the newest
            .order_by(
                Place.thumbnail_url.is_(None),
                func.coalesce(PlaceStats.popularity, 0.0).desc(),
                Place.id.desc(),
            )
            .limit(300)
        )
        if region is not None:
            stmt = stmt.where(Place.region_id == region.id)
        needle = (q or "").strip()
        if needle:
            # in SQL, before the 300-row cap: a search has to reach every sight, not just the first page
            like = "%" + needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            stmt = stmt.where(
                or_(
                    Place.name.ilike(like, escape="\\"),
                    Place.road_address.ilike(like, escape="\\"),
                    Place.address.ilike(like, escape="\\"),
                )
            )
        for p in (await self._s.scalars(stmt)).all():
            if (kind := type_of(p.category.code)) is not None:
                items.append(
                    dto.AttractionItem(
                        id=p.public_id,
                        kind="place",
                        type=kind,
                        name=p.name,
                        category=p.category.code,
                        lat=p.lat,
                        lng=p.lng,
                        address=p.road_address or p.address,
                        is_free=p.is_free,
                        price=p.price_per_person,
                        price_is_estimated=bool(p.price_is_estimated) and not p.is_free,
                        rating=p.stats.rating_avg if p.stats else None,
                        thumbnail_url=p.thumbnail_url,
                    )
                )
        day = on_date or datetime.now(self._tz).date()
        folded = needle.casefold()
        for e in (await self.events(region_slug, day, day)).items:
            if folded and folded not in f"{e.title} {e.address or ''}".casefold():
                continue
            if (kind := type_of(e.category or "culture.festival")) is not None:
                items.append(
                    dto.AttractionItem(
                        id=e.id,
                        kind="event",
                        type=kind,
                        name=e.title,
                        category=e.category or "culture.festival",
                        lat=e.lat,
                        lng=e.lng,
                        address=e.address,
                        is_free=e.is_free,
                        price=e.price,
                        starts_on=e.starts_on,
                        ends_on=e.ends_on,
                        thumbnail_url=e.thumbnail_url,
                    )
                )
        if len(wanted) > 1:
            # several kinds at once ("everything"): deal them out in turn. Ranked as one list the first
            # screen was markets only — every district's most visited place is its market.
            by_kind: dict[str, list[dto.AttractionItem]] = {}
            for item in items:
                by_kind.setdefault(item.type, []).append(item)
            turns = list(by_kind.values())
            items = [row[i] for i in range(max(map(len, turns), default=0)) for row in turns if i < len(row)]
        return dto.AttractionList(items=items)

    async def suggest(self, req: dto.PlaceSuggestRequest, user: User) -> dto.PlaceSuggestResponse:
        region = await self._region(req.region)
        category = await self._s.scalar(select(Category).where(Category.code == req.category))
        if category is None:
            raise errors.ValidationFailed(f"'{req.category}' 카테고리는 없어요.")
        place = Place(
            region_id=region.id,
            category_id=category.id,
            name=req.name,
            lat=req.lat,
            lng=req.lng,
            address=req.address,
            price_per_person=None if req.is_free else req.price_per_person,
            is_free=req.is_free,
            status="pending",
            images=[],
        )
        self._s.add(place)
        await self._s.flush()
        self._s.add(
            PlaceSource(
                place_id=place.id,
                provider="user",
                external_id=f"{user.public_id}:{place.public_id}",
                raw=req.model_dump(),
                fetched_at=utcnow(),
                content_hash="",
                match_confidence=1.0,
            )
        )
        self._s.add(
            PlaceRevision(
                place_id=place.id, admin_id=None, action="create", after=req.model_dump(), note=req.note
            )
        )
        await self._s.commit()
        return dto.PlaceSuggestResponse(id=place.public_id, status=place.status)


def _event_out(e: Event) -> dto.EventOut:
    return dto.EventOut(
        id=e.public_id,
        title=e.title,
        category=e.category.code if e.category else None,
        description=e.description,
        address=e.address,
        lat=e.lat,
        lng=e.lng,
        starts_on=e.starts_on,
        ends_on=e.ends_on,
        is_free=e.is_free,
        price=e.price,
        booking_url=e.booking_url,
        thumbnail_url=next(iter(e.images or []), None),
    )
