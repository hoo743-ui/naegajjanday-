from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import GeoPoint
from app.domain.routing.travel_time import haversine_m
from app.infra.db.models import Place, Region, RegionStat

HOTSPOT_REACH = 3  # × the hotspot's radius
DISTRICT_REACH = 2  # × the district's radius (a district's centre is not where its edge is)
DISTRICT_MIN_M = 8000
DISTRICT_FAR_M = 60000
NEIGHBOURHOOD_LEVEL = 4  # 동 · 읍 · 면: drawn over a district, owns no places (`region_stat` counts them)


class SqlRegionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get_by_slug(self, slug: str) -> Region | None:
        return await self._s.scalar(select(Region).where(Region.slug == slug))

    async def list_all(self) -> list[Region]:
        return list((await self._s.scalars(select(Region).order_by(Region.level, Region.name))).all())

    async def list_active(self, parent_slug: str | None, q: str | None) -> list[tuple[Region, int]]:
        counts = (
            select(Place.region_id, func.count(Place.id).label("n"))
            .where(Place.status == "approved")
            .group_by(Place.region_id)
            .subquery()
        )
        stmt = (
            select(Region, func.coalesce(counts.c.n, 0))
            .outerjoin(counts, counts.c.region_id == Region.id)
            .where(Region.status == "active")
            .order_by(Region.level, Region.name)
        )
        parent = await self.get_by_slug(parent_slug) if parent_slug else None
        if parent_slug:
            if parent is None:
                return []
            child_ids = select(Region.id).where(Region.parent_id == parent.id)
            stmt = stmt.where(or_(Region.parent_id == parent.id, Region.parent_id.in_(child_ids)))
        if not q and (parent is None or parent.level < NEIGHBOURHOOD_LEVEL - 2):
            # 1,400 of them: sent when a district is opened or a name is searched, not with every list
            stmt = stmt.where(Region.level < NEIGHBOURHOOD_LEVEL)
        if q:
            pattern = f"%{q.strip()}%"
            stmt = stmt.where(or_(Region.name.ilike(pattern), Region.slug.ilike(pattern)))
        rows = [(region, int(n)) for region, n in (await self._s.execute(stmt)).all()]
        return await self._with_descendants(rows)

    async def _with_descendants(self, rows: list[tuple[Region, int]]) -> list[tuple[Region, int]]:
        """A place belongs to its most specific region only, so parents add up their children."""
        own = (
            await self._s.execute(
                select(Place.region_id, func.count(Place.id))
                .where(Place.status == "approved")
                .group_by(Place.region_id)
            )
        ).all()
        parents = dict((await self._s.execute(select(Region.id, Region.parent_id))).tuples().all())
        total: dict[int, int] = {}
        for region_id, n in own:
            node: int | None = region_id
            hops = 0
            while node is not None and hops < 4:  # level 3 → 2 → 1; the bound also stops bad cycles
                total[node] = total.get(node, 0) + int(n)
                node, hops = parents.get(node), hops + 1
        stats = await self._s.execute(select(RegionStat.region_id, RegionStat.place_count))
        drawn = dict(stats.tuples().all())
        return [(region, total.get(region.id, 0) or int(drawn.get(region.id, 0))) for region, _own in rows]

    async def ids_under(self, region_id: int) -> list[int]:
        """The region and everything below it (a province → its districts → their hotspots)."""
        found, frontier = [region_id], [region_id]
        while frontier:
            rows = await self._s.scalars(select(Region.id).where(Region.parent_id.in_(frontier)))
            frontier = [i for i in rows.all() if i not in found]
            found.extend(frontier)
        return found

    async def nearest_active(self, point: GeoPoint) -> Region | None:
        """The neighbourhood a point belongs to: a hotspot when one is close, otherwise the district
        around it. Hotspots alone left most of the country with "no region nearby" — a station picked
        in the wizard, or a well-visited area of a whole-city trip, failed anywhere outside the 55 of them."""
        rows = (
            await self._s.scalars(select(Region).where(Region.status == "active", Region.level.in_([2, 3])))
        ).all()

        def reach(r: Region) -> float:
            return haversine_m(point, GeoPoint(r.center_lat, r.center_lng))

        hotspots = [r for r in rows if r.level == 3 and reach(r) <= r.radius_m * HOTSPOT_REACH]
        if hotspots:
            return min(hotspots, key=reach)
        districts = [
            r for r in rows if r.level == 2 and reach(r) <= max(r.radius_m * DISTRICT_REACH, DISTRICT_MIN_M)
        ]
        if districts:
            return min(districts, key=reach)
        # a wide rural district (an island, a county): its centre can be tens of km from its coast
        far = [r for r in rows if r.level == 2 and reach(r) <= DISTRICT_FAR_M]
        return min(far, key=reach, default=None)
