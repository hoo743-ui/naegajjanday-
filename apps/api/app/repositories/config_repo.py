from __future__ import annotations

from datetime import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import ScoringParams, ScoringProfile, Slot, Template
from app.infra.db.models import Category, CourseTemplate, Purpose, PurposeTagAffinity, Tag
from app.infra.db.models import ScoringProfile as ScoringProfileRow


def _min(t: time | None) -> int | None:
    return None if t is None else t.hour * 60 + t.minute


def to_template(row: CourseTemplate, purpose_code: str) -> Template:
    return Template(
        id=row.id,
        code=row.code,
        purpose_code=purpose_code,
        time_band=row.time_band,
        min_budget_per_person=row.min_budget_per_person,
        party_min=row.party_min,
        party_max=row.party_max,
        slots=tuple(
            Slot(
                position=s.position,
                course_role=s.course_role,
                budget_share=s.budget_share,
                is_optional=s.is_optional,
                is_order_flexible=s.is_order_flexible,
                earliest_start_min=_min(s.earliest_start),
                latest_start_min=_min(s.latest_start),
                min_slot_budget=s.min_slot_budget,
            )
            for s in row.slots
        ),
    )


class SqlConfigRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get_purpose(self, code: str, only_active: bool = True) -> Purpose | None:
        stmt = select(Purpose).where(Purpose.code == code)
        if only_active:
            stmt = stmt.where(Purpose.is_active.is_(True))
        return await self._s.scalar(stmt)

    async def list_purposes(self) -> list[Purpose]:
        stmt = select(Purpose).where(Purpose.is_active.is_(True)).order_by(Purpose.sort_order, Purpose.id)
        return list((await self._s.scalars(stmt)).all())

    async def template_rows(
        self, purpose_id: int | None = None, only_active: bool = True
    ) -> list[CourseTemplate]:
        stmt = select(CourseTemplate).order_by(CourseTemplate.id)
        if purpose_id is not None:
            stmt = stmt.where(CourseTemplate.purpose_id == purpose_id)
        if only_active:
            stmt = stmt.where(CourseTemplate.is_active.is_(True))
        return list((await self._s.scalars(stmt)).all())

    async def templates_for(self, purpose_id: int, purpose_code: str) -> list[Template]:
        return [to_template(r, purpose_code) for r in await self.template_rows(purpose_id)]

    async def profile_row(self, purpose_id: int) -> ScoringProfileRow | None:
        return await self._s.scalar(
            select(ScoringProfileRow).where(ScoringProfileRow.purpose_id == purpose_id)
        )

    async def scoring_profile(self, purpose_id: int, purpose_code: str) -> ScoringProfile:
        row = await self.profile_row(purpose_id)
        if row is None or not row.is_active:  # fall back to the doc 06 defaults
            return ScoringProfile(purpose_code, 0, {}, ScoringParams())
        return ScoringProfile(
            purpose_code, row.version, dict(row.weights), ScoringParams.from_dict(row.params)
        )

    async def tag_affinity(self, purpose_id: int) -> dict[str, float]:
        stmt = (
            select(Tag.name, PurposeTagAffinity.weight)
            .join(Tag, Tag.id == PurposeTagAffinity.tag_id)
            .where(PurposeTagAffinity.purpose_id == purpose_id)
        )
        return {name: weight for name, weight in (await self._s.execute(stmt)).all()}

    async def list_categories(self) -> list[Category]:
        return list((await self._s.scalars(select(Category).order_by(Category.code))).all())

    async def list_tags(self, group: str | None) -> list[Tag]:
        stmt = select(Tag).where(Tag.is_selectable.is_(True)).order_by(Tag.group, Tag.id)
        if group:
            stmt = stmt.where(Tag.group == group)
        return list((await self._s.scalars(stmt)).all())
