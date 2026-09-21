from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core import errors
from app.core.config import Settings
from app.infra.db.base import as_utc, utcnow
from app.infra.db.models import (
    Category,
    CourseStop,
    IngestionJob,
    Place,
    PlaceRevision,
    PlaceSource,
    PlaceTag,
    Region,
    SearchOutbox,
    Tag,
)
from app.infra.ingestion.pipeline import IngestionPipeline
from app.infra.ingestion.price import price_tier
from app.infra.ingestion.providers.file_provider import FileFormatError, FileProvider
from app.schemas import admin as dto
from app.schemas.common import decode_cursor, encode_cursor
from app.services.audit import AuditLogger

LOAD = (selectinload(Place.region), selectinload(Place.category), selectinload(Place.sources))
SNAPSHOT_FIELDS = (
    "name",
    "status",
    "lat",
    "lng",
    "address",
    "phone",
    "description",
    "thumbnail_url",
    "price_per_person",
    "is_free",
    "category_id",
)


def snapshot(place: Place) -> dict[str, Any]:
    return {f: getattr(place, f) for f in SNAPSHOT_FIELDS}


def place_out(p: Place) -> dto.AdminPlaceOut:
    return dto.AdminPlaceOut(
        id=p.public_id,
        name=p.name,
        region=p.region.slug,
        category=p.category.code,
        status=p.status,
        lat=p.lat,
        lng=p.lng,
        address=p.road_address or p.address,
        price_per_person=p.price_per_person,
        is_free=p.is_free,
        data_quality=p.data_quality,
        sources=sorted({s.provider for s in p.sources}),
        created_at=as_utc(p.created_at) or utcnow(),
    )


class AdminPlaceService:
    def __init__(self, settings: Settings, session: AsyncSession, audit: AuditLogger) -> None:
        self._settings = settings
        self._s = session
        self._audit = audit

    async def _get(self, public_id: str) -> Place:
        place = await self._s.scalar(select(Place).where(Place.public_id == public_id).options(*LOAD))
        if place is None:
            raise errors.PlaceNotFound()
        return place

    async def _category(self, code: str) -> Category:
        cat = await self._s.scalar(select(Category).where(Category.code == code))
        if cat is None:
            raise errors.ValidationFailed(f"'{code}' 카테고리는 없어요.")
        return cat

    def _revise(
        self, place: Place, action: str, before: dict[str, Any] | None, note: str | None = None
    ) -> None:
        self._s.add(
            PlaceRevision(
                place_id=place.id,
                admin_id=self._audit.actor.id,
                action=action,
                before=before,
                after=snapshot(place),
                note=note,
            )
        )
        self._s.add(SearchOutbox(entity="place", entity_id=place.id, op="upsert"))
        self._audit.record(
            f"place.{action}", "place", place.public_id, {"before": before, "after": snapshot(place)}
        )

    async def list(
        self, status: str | None, region: str | None, q: str | None, cursor: str | None, limit: int
    ) -> dto.AdminPlaceList:
        stmt = select(Place).options(*LOAD).order_by(Place.id.desc())
        if status:
            stmt = stmt.where(Place.status == status)
        if region:
            stmt = stmt.join(Region, Region.id == Place.region_id).where(Region.slug == region)
        if q:
            stmt = stmt.where(Place.name.ilike(f"%{q}%"))
        if (after := decode_cursor(cursor)) is not None:
            stmt = stmt.where(Place.id < after)
        rows = (await self._s.scalars(stmt.limit(limit + 1))).all()
        page = rows[:limit]
        return dto.AdminPlaceList(
            items=[place_out(p) for p in page],
            next_cursor=encode_cursor(page[-1].id) if len(rows) > limit and page else None,
        )

    async def set_status(
        self, public_id: str, status: str, action: str, note: str | None
    ) -> dto.AdminPlaceOut:
        place = await self._get(public_id)
        before = snapshot(place)
        place.status = status
        if status == "approved":
            place.approved_at = place.approved_at or utcnow()
            place.last_verified_at = utcnow()
        self._revise(place, action, before, note)
        await self._s.commit()
        return place_out(place)

    async def bulk_approve(self, ids: Sequence[str]) -> dto.BulkResult:
        rows = (await self._s.scalars(select(Place).where(Place.public_id.in_(ids)).options(*LOAD))).all()
        for place in rows:
            before = snapshot(place)
            place.status, place.approved_at = "approved", place.approved_at or utcnow()
            self._revise(place, "approve", before, "bulk")
        await self._s.commit()
        found = {p.public_id for p in rows}
        return dto.BulkResult(updated=len(rows), not_found=[i for i in ids if i not in found])

    async def create(self, body: dto.AdminPlaceCreate) -> dto.AdminPlaceOut:
        region = await self._s.scalar(select(Region).where(Region.slug == body.region))
        if region is None:
            raise errors.RegionNotFound()
        category = await self._category(body.category)
        place = Place(
            region_id=region.id,
            category_id=category.id,
            name=body.name,
            lat=body.lat,
            lng=body.lng,
            address=body.address,
            phone=body.phone,
            description=body.description,
            thumbnail_url=body.thumbnail_url,
            is_free=body.is_free,
            price_per_person=None if body.is_free else body.price_per_person,
            price_tier=price_tier(body.price_per_person, body.is_free),
            status="approved",
            approved_at=utcnow(),
            last_verified_at=utcnow(),
            images=[],
        )
        self._s.add(place)
        await self._s.flush()
        self._s.add(
            PlaceSource(
                place_id=place.id,
                provider="admin",
                external_id=place.public_id,
                raw=body.model_dump(),
                fetched_at=utcnow(),
                content_hash="",
                match_confidence=1.0,
            )
        )
        await self._set_tags(place.id, body.tags)
        await self._s.flush()
        place = await self._get(place.public_id)
        self._revise(place, "create", None)
        await self._s.commit()
        return place_out(place)

    async def _set_tags(self, place_id: int, tags: dict[str, float]) -> None:
        from sqlalchemy import delete

        await self._s.execute(delete(PlaceTag).where(PlaceTag.place_id == place_id))
        for name, weight in tags.items():
            tag = await self._s.scalar(select(Tag).where(Tag.name == name))
            if tag is None:
                raise errors.ValidationFailed(f"'{name}' 태그는 없어요.")
            self._s.add(PlaceTag(place_id=place_id, tag_id=tag.id, weight=weight, source="admin"))

    async def patch(self, public_id: str, body: dto.AdminPlacePatch) -> dto.AdminPlaceOut:
        place = await self._get(public_id)
        before = snapshot(place)
        data = body.model_dump(exclude_unset=True)
        if (code := data.pop("category", None)) is not None:
            place.category_id = (await self._category(code)).id
        if (tags := data.pop("tags", None)) is not None:
            await self._set_tags(place.id, tags)
        for key, value in data.items():
            setattr(place, key, value)
        if "price_per_person" in data:  # an operator-entered price replaces the category prior
            place.price_is_estimated = False
        if place.is_free:
            place.price_per_person = None
        place.price_tier = price_tier(place.price_per_person, place.is_free)
        if place.status == "approved":
            place.approved_at = place.approved_at or utcnow()
        self._revise(place, "edit", before)
        await self._s.commit()
        return place_out(await self._get(public_id))

    async def merge(self, public_id: str, body: dto.MergeRequest) -> dto.AdminPlaceOut:
        """Duplicate merge: sources and course history move to the survivor, the duplicate is hidden."""
        survivor, duplicate = await self._get(public_id), await self._get(body.duplicate_id)
        if survivor.id == duplicate.id:
            raise errors.ValidationFailed("같은 장소끼리는 병합할 수 없어요.")
        before = snapshot(survivor)
        await self._s.execute(
            update(PlaceSource).where(PlaceSource.place_id == duplicate.id).values(place_id=survivor.id)
        )
        await self._s.execute(
            update(CourseStop).where(CourseStop.place_id == duplicate.id).values(place_id=survivor.id)
        )
        for field in ("address", "road_address", "phone", "description", "thumbnail_url", "price_per_person"):
            if getattr(survivor, field) in (None, "") and getattr(duplicate, field) not in (None, ""):
                setattr(survivor, field, getattr(duplicate, field))
        dup_before = snapshot(duplicate)
        duplicate.status = "hidden"
        self._revise(duplicate, "merge", dup_before, f"merged into {survivor.public_id}")
        self._revise(survivor, "merge", before, body.note or f"absorbed {duplicate.public_id}")
        await self._s.commit()
        return place_out(await self._get(public_id))

    async def revisions(self, public_id: str) -> dto.RevisionList:
        place = await self._get(public_id)
        rows = await self._s.scalars(
            select(PlaceRevision).where(PlaceRevision.place_id == place.id).order_by(PlaceRevision.id.desc())
        )
        return dto.RevisionList(
            items=[
                dto.RevisionOut(
                    id=r.id,
                    action=r.action,
                    admin_id=r.admin_id,
                    before=r.before,
                    after=r.after,
                    note=r.note,
                    created_at=as_utc(r.created_at) or utcnow(),
                )
                for r in rows.all()
            ]
        )

    async def import_file(self, path: Path, region_slug: str) -> dto.IngestionJobOut:
        """CSV/JSON upload → `file` provider job through the normal ingestion pipeline."""
        from app.services.admin_ingestion_service import job_out

        region = await self._s.scalar(select(Region).where(Region.slug == region_slug))
        if region is None:
            raise errors.RegionNotFound()
        job = IngestionJob(
            provider="file", region_id=region.id, job_type="full", params={"filename": path.name}
        )
        self._s.add(job)
        await self._s.flush()
        try:
            provider = FileProvider(path)
            _ = provider.payload
        except (FileFormatError, ValueError) as exc:
            raise errors.ValidationFailed(str(exc)) from exc
        await IngestionPipeline(self._s, self._settings.trusted_providers).run(provider, region, job)
        self._audit.record(
            "place.import", "ingestion_job", job.id, {"file": path.name, "region": region_slug}
        )
        await self._s.commit()
        return job_out(job, region_slug)
