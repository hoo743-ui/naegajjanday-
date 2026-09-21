"""Meta lookups. Everything comes from the DB — opening a region never needs a deploy."""

from __future__ import annotations

import math

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import errors
from app.core.cache import Cache
from app.domain.signature import Signature, get_signature_rules
from app.infra.db.base import utcnow
from app.infra.db.models import Banner, Region
from app.repositories.config_repo import SqlConfigRepository
from app.repositories.region_repo import SqlRegionRepository
from app.schemas import meta as dto
from app.schemas.common import LatLng
from app.services import signature_service

META_TTL_S = 3600


class MetaService:
    def __init__(self, session: AsyncSession, cache: Cache) -> None:
        self._s = session
        self._cache = cache
        self._regions = SqlRegionRepository(session)
        self._config = SqlConfigRepository(session)

    async def signature(self, slug: str) -> dto.LocalSignature:
        region = await self._regions.get_by_slug(slug)
        if region is None:
            raise errors.RegionNotFound(f"'{slug}' 지역을 찾을 수 없어요.")
        signature = await signature_service.load(self._s, region.id)
        return local_signature_out(
            region.name, signature.strong(get_signature_rules().auto_focus_min_strength)
        )

    async def regions(self, parent: str | None, q: str | None) -> dto.RegionList:
        key = f"region:list:{parent or ''}:{q or ''}"
        if (cached := await self._cache.get(key)) is not None:
            return dto.RegionList.model_validate(cached)
        items = [
            dto.RegionOut(
                slug=r.slug,
                name=r.name,
                level=r.level,
                center=LatLng(lat=r.center_lat, lng=r.center_lng),
                radius_m=r.radius_m,
                parent=dto.RegionParent(slug=r.parent.slug, name=r.parent.name) if r.parent else None,
                place_count=n,
            )
            for r, n in await self._regions.list_active(parent, q)
        ]
        out = dto.RegionList(items=items)
        await self._cache.set(key, out.model_dump(mode="json"), META_TTL_S)
        return out

    async def purposes(self) -> dto.PurposeList:
        if (cached := await self._cache.get("purpose:list")) is not None:
            return dto.PurposeList.model_validate(cached)
        items = []
        for p in await self._config.list_purposes():
            templates = await self._config.template_rows(p.id)
            # budget_min/max are totals for the purpose's usual party (a date = two people)
            party = min((t.party_min for t in templates), default=1)
            party = max(party, min(2, max((t.party_max for t in templates), default=1)))
            items.append(
                dto.PurposeOut(
                    code=p.code,
                    name=p.name,
                    icon=p.icon,
                    description=p.description,
                    recommended_budget=dto.BudgetRange(min=p.budget_min, max=p.budget_max),
                    budget_per_person=_per_person(p.budget_min, p.budget_max, party),
                    default_party_size=party,
                    max_party_size=max((t.party_max for t in templates), default=None),
                    time_bands=sorted({t.time_band for t in templates}),
                    min_budget_per_person=min((t.min_budget_per_person for t in templates), default=None),
                )
            )
        out = dto.PurposeList(items=items)
        await self._cache.set("purpose:list", out.model_dump(mode="json"), META_TTL_S)
        return out

    async def categories(self) -> dto.CategoryList:
        rows = await self._config.list_categories()
        nodes = {
            c.id: dto.CategoryOut(
                code=c.code, name=c.name, course_role=c.course_role, default_stay_min=c.default_stay_min
            )
            for c in rows
        }
        roots: list[dto.CategoryOut] = []
        for c in rows:
            (nodes[c.parent_id].children if c.parent_id in nodes else roots).append(nodes[c.id])
        return dto.CategoryList(items=roots)

    async def tags(self, group: str | None) -> dto.TagList:
        return dto.TagList(
            items=[dto.TagOut(name=t.name, group=t.group) for t in await self._config.list_tags(group)]
        )

    async def banners(self, placement: str | None, region_slug: str | None) -> dto.BannerList:
        now = utcnow()
        stmt = (
            select(Banner)
            .where(Banner.is_active.is_(True))
            .where(or_(Banner.starts_at.is_(None), Banner.starts_at <= now))
            .where(or_(Banner.ends_at.is_(None), Banner.ends_at >= now))
            .order_by(Banner.priority.desc(), Banner.id.desc())
        )
        if placement:
            stmt = stmt.where(Banner.placement == placement)
        region_id = None
        if region_slug:
            region_id = await self._s.scalar(select(Region.id).where(Region.slug == region_slug))
        stmt = stmt.where(or_(Banner.region_id.is_(None), Banner.region_id == region_id))
        rows = (await self._s.scalars(stmt)).all()
        return dto.BannerList(
            items=[
                dto.BannerOut(
                    id=b.id,
                    title=b.title,
                    image_url=b.image_url,
                    link_url=b.link_url,
                    placement=b.placement,
                    priority=b.priority,
                )
                for b in rows
            ]
        )

    async def invalidate(self) -> int:
        return await self._cache.delete_prefix("region:list") + await self._cache.delete_prefix(
            "purpose:list"
        )


def _per_person(total_min: int | None, total_max: int | None, party: int) -> dto.PerPersonBudget:
    """Totals → per person, rounded to 1,000. `typical` is the geometric mean: spending is
    log-distributed, so the arithmetic midpoint (3만~12만 → 7.5만) lands far above what people pick."""
    if not total_min or not total_max:
        return dto.PerPersonBudget()
    lo, hi = total_min / party, total_max / party

    def r(v: float) -> int:
        return int(round(v / 1000.0) * 1000)

    return dto.PerPersonBudget(min=r(lo), max=r(hi), typical=r(math.sqrt(lo * hi)))


def local_signature_out(region_name: str, signature: Signature) -> dto.LocalSignature:
    return dto.LocalSignature(
        region=region_name,
        shops=signature.shops,
        specialties=[
            dto.LocalSpecialty(word=s.word, count=s.count, lift=s.lift) for s in signature.specialties
        ],
        sights=[dto.LocalSight(name=s.name, mentions=s.mentions) for s in signature.sights],
    )
