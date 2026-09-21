"""Idempotent upsert of configuration DATA (regions, categories, tags, purposes → templates, scoring
profiles, tag affinities) from `data/seed/*.json`. Nothing here knows any concrete region or purpose."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.db.models import (
    Category,
    CourseTemplate,
    Purpose,
    PurposeTagAffinity,
    Region,
    ScoringProfile,
    Tag,
    TemplateSlot,
)
from app.infra.ingestion.pipeline import parse_time


@dataclass(slots=True)
class ConfigReport:
    regions: int = 0
    categories: int = 0
    tags: int = 0
    purposes: int = 0
    templates: int = 0


class ConfigFormatError(ValueError):
    pass


def _load(path: Path, key: str) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get(key) if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise ConfigFormatError(f"{path.name}: expected a '{key}' array")
    return rows


async def load_config(session: AsyncSession, seed_dir: Path) -> ConfigReport:
    report = ConfigReport()
    report.categories = await upsert_categories(session, _load(seed_dir / "categories.json", "categories"))
    report.tags = await upsert_tags(session, _load(seed_dir / "tags.json", "tags"))
    report.regions = await upsert_regions(session, _load(seed_dir / "regions.json", "regions"))
    report.purposes, report.templates = await upsert_purposes(
        session, _load(seed_dir / "purposes.json", "purposes")
    )
    return report


async def upsert_regions(session: AsyncSession, rows: list[dict[str, Any]]) -> int:
    by_slug = {r.slug: r for r in (await session.scalars(select(Region))).all()}
    for row in rows:
        region = by_slug.get(row["slug"])
        if region is None:
            region = Region(slug=row["slug"])
            session.add(region)
            by_slug[row["slug"]] = region
        parent_slug = row.get("parent")
        if parent_slug and parent_slug not in by_slug:
            raise ConfigFormatError(
                f"region {row['slug']}: unknown parent '{parent_slug}' (list parents first)"
            )
        region.name, region.level = row["name"], int(row["level"])
        region.center_lat, region.center_lng = float(row["center_lat"]), float(row["center_lng"])
        region.radius_m = int(row.get("radius_m") or 1200)
        region.area_code = row.get("area_code")
        region.status = row.get("status") or "draft"
        region.search_keywords = list(row.get("search_keywords") or [])
        await session.flush()
        region.parent_id = by_slug[parent_slug].id if parent_slug else None
    await session.flush()
    return len(rows)


async def upsert_categories(session: AsyncSession, rows: list[dict[str, Any]]) -> int:
    by_code = {c.code: c for c in (await session.scalars(select(Category))).all()}
    for row in rows:
        cat = by_code.get(row["code"])
        if cat is None:
            cat = Category(code=row["code"])
            session.add(cat)
            by_code[row["code"]] = cat
        parent = row.get("parent")
        if parent and parent not in by_code:
            raise ConfigFormatError(f"category {row['code']}: unknown parent '{parent}'")
        cat.name, cat.course_role = row["name"], row["course_role"]
        cat.default_stay_min = int(row.get("default_stay_min") or 60)
        cat.provider_mapping = dict(row.get("provider_mapping") or {})
        await session.flush()
        cat.parent_id = by_code[parent].id if parent else None
    await session.flush()
    return len(rows)


async def upsert_tags(session: AsyncSession, rows: list[dict[str, Any]]) -> int:
    by_name = {t.name: t for t in (await session.scalars(select(Tag))).all()}
    for row in rows:
        tag = by_name.get(row["name"])
        if tag is None:
            tag = Tag(name=row["name"])
            session.add(tag)
            by_name[row["name"]] = tag
        tag.group = row.get("group") or "feature"
        tag.is_selectable = bool(row.get("is_selectable", True))
    await session.flush()
    return len(rows)


async def upsert_purposes(session: AsyncSession, rows: list[dict[str, Any]]) -> tuple[int, int]:
    tags = {t.name: t for t in (await session.scalars(select(Tag))).all()}
    by_code = {p.code: p for p in (await session.scalars(select(Purpose))).all()}
    templates = 0
    for row in rows:
        purpose = by_code.get(row["code"])
        if purpose is None:
            purpose = Purpose(code=row["code"], name=row["name"])
            session.add(purpose)
        purpose.name, purpose.icon, purpose.description = row["name"], row.get("icon"), row.get("description")
        purpose.budget_min, purpose.budget_max = row.get("budget_min"), row.get("budget_max")
        purpose.sort_order = int(row.get("sort_order") or 0)
        purpose.is_active = bool(row.get("is_active", True))
        await session.flush()

        if sp := row.get("scoring_profile"):
            profile = await session.scalar(
                select(ScoringProfile).where(ScoringProfile.purpose_id == purpose.id)
            )
            if profile is None:
                profile = ScoringProfile(purpose_id=purpose.id)
                session.add(profile)
            profile.version = int(sp.get("version") or 1)
            profile.weights, profile.params = dict(sp["weights"]), dict(sp.get("params") or {})
            profile.is_active, profile.experiment_key = True, sp.get("experiment_key")

        if "tag_affinities" in row:
            await session.execute(
                delete(PurposeTagAffinity).where(PurposeTagAffinity.purpose_id == purpose.id)
            )
            for name, weight in (row["tag_affinities"] or {}).items():
                if name not in tags:
                    raise ConfigFormatError(f"purpose {row['code']}: unknown tag '{name}' in tag_affinities")
                w = max(-1.0, min(1.0, float(weight)))
                session.add(PurposeTagAffinity(purpose_id=purpose.id, tag_id=tags[name].id, weight=w))

        for t in row.get("templates") or []:
            await upsert_template(session, purpose.id, t)
            templates += 1
    await session.flush()
    return len(rows), templates


async def upsert_template(session: AsyncSession, purpose_id: int, t: dict[str, Any]) -> None:
    shares = sum(float(s["budget_share"]) for s in t["slots"])
    if t["slots"] and abs(shares - 1.0) > 0.01:
        raise ConfigFormatError(f"template {t['code']}: budget_share must sum to 1 (got {shares:.3f})")
    template = await session.scalar(select(CourseTemplate).where(CourseTemplate.code == t["code"]))
    if template is None:
        template = CourseTemplate(
            code=t["code"], purpose_id=purpose_id, name=t["name"], time_band=t["time_band"]
        )
        session.add(template)
    template.purpose_id, template.name, template.time_band = purpose_id, t["name"], t["time_band"]
    template.min_budget_per_person = int(t.get("min_budget_per_person") or 0)
    template.party_min, template.party_max = int(t.get("party_min") or 1), int(t.get("party_max") or 8)
    template.is_active = bool(t.get("is_active", True))
    await session.flush()
    await session.execute(delete(TemplateSlot).where(TemplateSlot.template_id == template.id))
    for position, s in enumerate(t["slots"], start=1):
        session.add(
            TemplateSlot(
                template_id=template.id,
                position=position,
                course_role=s["course_role"],
                budget_share=float(s["budget_share"]),
                is_optional=bool(s.get("is_optional")),
                is_order_flexible=bool(s.get("is_order_flexible")),
                earliest_start=parse_time(s.get("earliest_start")),
                latest_start=parse_time(s.get("latest_start")),
                min_slot_budget=s.get("min_slot_budget"),
            )
        )
    await session.flush()
    await session.refresh(template, ["slots"])
