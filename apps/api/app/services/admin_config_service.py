"""Admin: regions, scoring profiles, templates, tag affinities — the data that drives recommendation."""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import errors
from app.core.cache import Cache
from app.infra.db.models import CourseTemplate, Place, Purpose, PurposeTagAffinity, Region, Tag
from app.infra.db.models import ScoringProfile as ScoringProfileRow
from app.infra.ingestion.config_loader import ConfigFormatError, upsert_regions, upsert_template
from app.repositories.config_repo import SqlConfigRepository
from app.schemas import admin as dto
from app.services.audit import AuditLogger

META_PREFIXES = ("region:list", "purpose:list", "course:")


def _hhmm(value: object) -> str | None:
    return value.strftime("%H:%M") if value is not None else None  # type: ignore[attr-defined]


def template_out(t: CourseTemplate, purpose_code: str) -> dto.TemplateOut:
    return dto.TemplateOut(
        code=t.code, purpose=purpose_code, name=t.name, time_band=t.time_band,
        min_budget_per_person=t.min_budget_per_person, party_min=t.party_min, party_max=t.party_max,
        is_active=t.is_active,
        slots=[
            dto.SlotBody(
                course_role=s.course_role, budget_share=s.budget_share, is_optional=s.is_optional,
                is_order_flexible=s.is_order_flexible, earliest_start=_hhmm(s.earliest_start),
                latest_start=_hhmm(s.latest_start), min_slot_budget=s.min_slot_budget,
            )
            for s in t.slots
        ],
    )  # fmt: skip


class AdminConfigService:
    def __init__(self, session: AsyncSession, cache: Cache, audit: AuditLogger) -> None:
        self._s = session
        self._cache = cache
        self._audit = audit
        self._config = SqlConfigRepository(session)

    async def _flush_meta(self) -> None:
        for prefix in META_PREFIXES:  # admin edits take effect immediately
            await self._cache.delete_prefix(prefix)

    # --- regions -----------------------------------------------------------------------------

    async def _region(self, slug: str) -> Region:
        region = await self._s.scalar(select(Region).where(Region.slug == slug))
        if region is None:
            raise errors.RegionNotFound()
        return region

    async def _region_out(self, r: Region) -> dto.AdminRegionOut:
        counts = await self._s.execute(
            select(Place.status, func.count(Place.id)).where(Place.region_id == r.id).group_by(Place.status)
        )
        return dto.AdminRegionOut(
            slug=r.slug, name=r.name, level=r.level, parent=r.parent.slug if r.parent else None,
            center_lat=r.center_lat, center_lng=r.center_lng, radius_m=r.radius_m, area_code=r.area_code,
            status=r.status, search_keywords=list(r.search_keywords or []),
            place_counts={status: n for status, n in counts.all()},
        )  # fmt: skip

    async def list_regions(self) -> dto.AdminRegionList:
        rows = (await self._s.scalars(select(Region).order_by(Region.level, Region.slug))).all()
        return dto.AdminRegionList(items=[await self._region_out(r) for r in rows])

    async def create_region(self, body: dto.RegionIn) -> dto.AdminRegionOut:
        if await self._s.scalar(select(Region.id).where(Region.slug == body.slug)) is not None:
            raise errors.Conflict(f"'{body.slug}' 지역이 이미 있어요.")
        try:
            await upsert_regions(self._s, [body.model_dump()])
        except ConfigFormatError as exc:
            raise errors.ValidationFailed(str(exc)) from exc
        self._audit.record("region.create", "region", body.slug, {"after": body.model_dump()})
        await self._s.commit()
        await self._flush_meta()
        return await self._region_out(await self._region(body.slug))

    async def patch_region(self, slug: str, body: dto.RegionPatch) -> dto.AdminRegionOut:
        region = await self._region(slug)
        changes = body.model_dump(exclude_unset=True)
        before = {k: getattr(region, k) for k in changes}
        for key, value in changes.items():
            setattr(region, key, value)
        self._audit.record("region.update", "region", slug, {"before": before, "after": changes})
        await self._s.commit()
        await self._flush_meta()
        return await self._region_out(region)

    async def activate_region(self, slug: str) -> dto.AdminRegionOut:
        region = await self._region(slug)
        approved = await self._s.scalar(
            select(func.count(Place.id)).where(Place.region_id == region.id, Place.status == "approved")
        )
        if not approved:
            raise errors.Conflict("승인된 장소가 하나도 없어서 활성화할 수 없어요.")
        before = region.status
        region.status = "active"
        self._audit.record("region.activate", "region", slug, {"before": before, "after": "active"})
        await self._s.commit()
        await self._flush_meta()
        return await self._region_out(region)

    # --- scoring profiles --------------------------------------------------------------------

    async def _purpose(self, code: str) -> Purpose:
        purpose = await self._config.get_purpose(code, only_active=False)
        if purpose is None:
            raise errors.PurposeNotFound()
        return purpose

    async def get_profile(self, purpose_code: str) -> dto.ScoringProfileOut:
        purpose = await self._purpose(purpose_code)
        row = await self._config.profile_row(purpose.id)
        if row is None:
            raise errors.NotFound("이 목적에는 아직 스코어링 프로필이 없어요.")
        return dto.ScoringProfileOut(
            purpose=purpose.code, version=row.version, weights=row.weights, params=row.params,
            is_active=row.is_active, experiment_key=row.experiment_key,
        )  # fmt: skip

    async def put_profile(self, purpose_code: str, body: dto.ScoringProfileBody) -> dto.ScoringProfileOut:
        purpose = await self._purpose(purpose_code)
        row = await self._config.profile_row(purpose.id)
        before = None
        if row is None:
            row = ScoringProfileRow(purpose_id=purpose.id, version=0, weights={}, params={})
            self._s.add(row)
        else:
            before = {"version": row.version, "weights": row.weights, "params": row.params}
        row.version += 1  # every edit is a new version; recommendation_log records which one was used
        # Only what the caller actually sent. The admin page saves weights alone; treating the omitted
        # `params` as {} silently wiped every tuned parameter (styles, variants, beam width …) on each save.
        sent = body.model_fields_set
        row.weights = body.weights
        if "params" in sent:
            row.params = body.params
        if "is_active" in sent:
            row.is_active = body.is_active
        if "experiment_key" in sent:
            row.experiment_key = body.experiment_key
        self._audit.record(
            "scoring_profile.update",
            "scoring_profile",
            purpose.code,
            {"before": before, "after": body.model_dump()},
        )
        await self._s.commit()
        await self._flush_meta()
        return await self.get_profile(purpose_code)

    # --- templates ---------------------------------------------------------------------------

    async def list_templates(self, purpose_code: str | None) -> dto.TemplateList:
        purposes = {p.id: p.code for p in (await self._s.scalars(select(Purpose))).all()}
        purpose_id = (await self._purpose(purpose_code)).id if purpose_code else None
        rows = await self._config.template_rows(purpose_id, only_active=False)
        return dto.TemplateList(items=[template_out(t, purposes[t.purpose_id]) for t in rows])

    async def create_template(self, body: dto.TemplateIn) -> dto.TemplateOut:
        purpose = await self._purpose(body.purpose)
        if (
            await self._s.scalar(select(CourseTemplate.id).where(CourseTemplate.code == body.code))
            is not None
        ):
            raise errors.Conflict(f"'{body.code}' 템플릿이 이미 있어요.")
        await upsert_template(self._s, purpose.id, body.model_dump())
        self._audit.record("template.create", "course_template", body.code, {"after": body.model_dump()})
        await self._s.commit()
        await self._flush_meta()
        return await self._template(body.code)

    async def _template(self, code: str) -> dto.TemplateOut:
        row = await self._s.scalar(select(CourseTemplate).where(CourseTemplate.code == code))
        if row is None:
            raise errors.NotFound("템플릿을 찾을 수 없어요.")
        purpose = await self._s.get(Purpose, row.purpose_id)
        return template_out(row, purpose.code if purpose else "")

    async def patch_template(self, code: str, body: dto.TemplatePatch) -> dto.TemplateOut:
        current = await self._template(code)
        changes = body.model_dump(exclude_unset=True)
        merged = {**current.model_dump(), **changes}
        try:
            validated = dto.TemplateIn.model_validate(merged)
        except ValueError as exc:
            raise errors.ValidationFailed(str(exc)) from exc
        purpose = await self._purpose(validated.purpose)
        await upsert_template(self._s, purpose.id, validated.model_dump())
        self._audit.record("template.update", "course_template", code, {"changes": changes})
        await self._s.commit()
        await self._flush_meta()
        return await self._template(code)

    # --- tag affinities ----------------------------------------------------------------------

    async def get_affinities(self, purpose_code: str) -> dto.TagAffinitiesBody:
        purpose = await self._purpose(purpose_code)
        return dto.TagAffinitiesBody(affinities=await self._config.tag_affinity(purpose.id))

    async def put_affinities(self, purpose_code: str, body: dto.TagAffinitiesBody) -> dto.TagAffinitiesBody:
        purpose = await self._purpose(purpose_code)
        before = await self._config.tag_affinity(purpose.id)
        tags = {t.name: t.id for t in (await self._s.scalars(select(Tag))).all()}
        unknown = sorted(set(body.affinities) - set(tags))
        if unknown:
            raise errors.ValidationFailed(f"없는 태그예요: {', '.join(unknown)}")
        await self._s.execute(delete(PurposeTagAffinity).where(PurposeTagAffinity.purpose_id == purpose.id))
        for name, weight in body.affinities.items():
            self._s.add(PurposeTagAffinity(purpose_id=purpose.id, tag_id=tags[name], weight=weight))
        self._audit.record(
            "tag_affinity.update", "purpose", purpose.code, {"before": before, "after": body.affinities}
        )
        await self._s.commit()
        await self._flush_meta()
        return await self.get_affinities(purpose_code)
