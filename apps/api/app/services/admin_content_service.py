"""Admin: events and banners CRUD."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core import errors
from app.domain.anchors import university_rules
from app.infra.db.models import Banner, Category, Event, Place, Region
from app.repositories.place_repo import SqlPlaceRepository
from app.schemas import admin as dto
from app.services.audit import AuditLogger


class AdminContentService:
    def __init__(self, session: AsyncSession, audit: AuditLogger) -> None:
        self._s = session
        self._audit = audit

    async def _region(self, slug: str) -> Region:
        region = await self._s.scalar(select(Region).where(Region.slug == slug))
        if region is None:
            raise errors.RegionNotFound()
        return region

    async def _slugs(self) -> dict[int, str]:
        return {i: s for i, s in (await self._s.execute(select(Region.id, Region.slug))).all()}

    # --- events ------------------------------------------------------------------------------

    @staticmethod
    def _event_out(e: Event, slugs: dict[int, str]) -> dto.AdminEventOut:
        return dto.AdminEventOut(
            id=e.public_id, region=slugs.get(e.region_id, ""), title=e.title,
            category=e.category.code if e.category else None, description=e.description, address=e.address,
            lat=e.lat, lng=e.lng, starts_on=e.starts_on, ends_on=e.ends_on, is_free=e.is_free, price=e.price,
            booking_url=e.booking_url, status=e.status, provider=e.provider,
            start_time=e.start_time, end_time=e.end_time, priority=e.priority or 0,
            university=e.anchor_place.public_id if e.anchor_place else None,
            university_name=e.anchor_place.name if e.anchor_place else None,
        )  # fmt: skip

    async def _event(self, public_id: str) -> Event:
        event = await self._s.scalar(
            select(Event)
            .where(Event.public_id == public_id)
            .options(selectinload(Event.category), selectinload(Event.anchor_place))
        )
        if event is None:
            raise errors.NotFound("이벤트를 찾을 수 없어요.")
        return event

    async def list_events(self, region: str | None, status: str | None) -> dto.AdminEventList:
        stmt = (
            select(Event)
            .options(selectinload(Event.category), selectinload(Event.anchor_place))
            .order_by(Event.starts_on.desc())
            .limit(500)
        )
        if region:
            stmt = stmt.where(Event.region_id == (await self._region(region)).id)
        if status:
            stmt = stmt.where(Event.status == status)
        slugs = await self._slugs()
        return dto.AdminEventList(
            items=[self._event_out(e, slugs) for e in (await self._s.scalars(stmt)).all()]
        )

    async def create_event(self, body: dto.EventIn) -> dto.AdminEventOut:
        region = await self._region(body.region)
        category_id = None
        if body.category:
            category_id = await self._s.scalar(select(Category.id).where(Category.code == body.category))
            if category_id is None:
                raise errors.ValidationFailed(f"'{body.category}' 카테고리는 없어요.")
        campus = await self._campus(body.university) if body.university else None
        if (body.lat is None or body.lng is None) and campus is None:
            raise errors.ValidationFailed("위치(lat · lng)나 대학교(university) 중 하나는 필요해요.")
        fields = body.model_dump(exclude={"region", "category", "university", "lat", "lng"})
        event = Event(
            region_id=region.id, category_id=category_id, provider="admin", images=[],
            anchor_place_id=campus.id if campus else None,
            lat=body.lat if body.lat is not None else campus.lat,  # type: ignore[union-attr]
            lng=body.lng if body.lng is not None else campus.lng,  # type: ignore[union-attr]
            **fields,
        )  # fmt: skip
        self._s.add(event)
        await self._s.flush()
        self._audit.record("event.create", "event", event.public_id, {"after": body.model_dump(mode="json")})
        await self._s.commit()
        return self._event_out(await self._event(event.public_id), await self._slugs())

    async def patch_event(self, public_id: str, body: dto.EventPatch) -> dto.AdminEventOut:
        event = await self._event(public_id)
        changes = body.model_dump(exclude_unset=True)
        for key, value in changes.items():
            setattr(event, key, value)
        if event.ends_on < event.starts_on:
            raise errors.ValidationFailed("ends_on 은 starts_on 이후여야 해요.")
        self._audit.record(
            "event.update", "event", public_id, {"changes": body.model_dump(mode="json", exclude_unset=True)}
        )
        await self._s.commit()
        return self._event_out(event, await self._slugs())

    async def _campus(self, public_id: str) -> Place:
        """docs/34: the campus a university festival belongs to."""
        campus = await SqlPlaceRepository(self._s).campus(public_id, str(university_rules()["category"]))
        if campus is None:
            raise errors.ValidationFailed(
                f"'{public_id}' 대학교는 없어요. /meta/universities 에서 id 를 골라 주세요."
            )
        return campus

    async def delete_event(self, public_id: str) -> None:
        event = await self._event(public_id)
        await self._s.delete(event)
        self._audit.record("event.delete", "event", public_id, {"title": event.title})
        await self._s.commit()

    # --- banners -----------------------------------------------------------------------------

    @staticmethod
    def _banner_out(b: Banner, slugs: dict[int, str]) -> dto.AdminBannerOut:
        return dto.AdminBannerOut(
            id=b.id, title=b.title, image_url=b.image_url, link_url=b.link_url, placement=b.placement,
            region=slugs.get(b.region_id) if b.region_id else None, starts_at=b.starts_at, ends_at=b.ends_at,
            priority=b.priority, is_active=b.is_active,
        )  # fmt: skip

    async def _banner(self, banner_id: int) -> Banner:
        banner = await self._s.get(Banner, banner_id)
        if banner is None:
            raise errors.NotFound("배너를 찾을 수 없어요.")
        return banner

    async def list_banners(self) -> dto.AdminBannerList:
        rows = (
            await self._s.scalars(select(Banner).order_by(Banner.priority.desc(), Banner.id.desc()))
        ).all()
        slugs = await self._slugs()
        return dto.AdminBannerList(items=[self._banner_out(b, slugs) for b in rows])

    async def create_banner(self, body: dto.BannerIn) -> dto.AdminBannerOut:
        region_id = (await self._region(body.region)).id if body.region else None
        banner = Banner(region_id=region_id, **body.model_dump(exclude={"region"}))
        self._s.add(banner)
        await self._s.flush()
        self._audit.record("banner.create", "banner", banner.id, {"after": body.model_dump(mode="json")})
        await self._s.commit()
        return self._banner_out(banner, await self._slugs())

    async def patch_banner(self, banner_id: int, body: dto.BannerPatch) -> dto.AdminBannerOut:
        banner = await self._banner(banner_id)
        for key, value in body.model_dump(exclude_unset=True).items():
            setattr(banner, key, value)
        self._audit.record(
            "banner.update",
            "banner",
            banner_id,
            {"changes": body.model_dump(mode="json", exclude_unset=True)},
        )
        await self._s.commit()
        return self._banner_out(banner, await self._slugs())

    async def delete_banner(self, banner_id: int) -> None:
        banner = await self._banner(banner_id)
        await self._s.delete(banner)
        self._audit.record("banner.delete", "banner", banner_id, {"title": banner.title})
        await self._s.commit()
