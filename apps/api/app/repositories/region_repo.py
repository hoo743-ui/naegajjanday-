from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import GeoPoint
from app.domain.routing.travel_time import haversine_m
from app.infra.db.models import Place, Region


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
        if parent_slug:
            parent = await self.get_by_slug(parent_slug)
            if parent is None:
                return []
            child_ids = select(Region.id).where(Region.parent_id == parent.id)
            stmt = stmt.where(or_(Region.parent_id == parent.id, Region.parent_id.in_(child_ids)))
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
        return [(region, total.get(region.id, 0)) for region, _own in rows]

    async def nearest_active(self, point: GeoPoint) -> Region | None:
        rows = (
            await self._s.scalars(select(Region).where(Region.status == "active", Region.level == 3))
        ).all()
        best = min(rows, key=lambda r: haversine_m(point, GeoPoint(r.center_lat, r.center_lng)), default=None)
        if best is None:
            return None
        dist = haversine_m(point, GeoPoint(best.center_lat, best.center_lng))
        return best if dist <= best.radius_m * 3 else None
