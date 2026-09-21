"""Recommendation statistics straight from `recommendation_log` / `place_stats` (doc 06 §8)."""

from __future__ import annotations

import math
from collections import Counter
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.db.base import as_utc
from app.infra.db.models import Category, Course, Place, PlaceStats, Purpose, RecommendationLog, Region
from app.schemas import admin as dto

REROLL_WINDOW = timedelta(minutes=10)
MAX_ROWS = 50_000


def percentile(sorted_values: list[int], q: float) -> int | None:
    if not sorted_values:
        return None
    return sorted_values[min(len(sorted_values) - 1, math.ceil(q * len(sorted_values)) - 1)]


class AnalyticsService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def recommendations(self, date_from: date, date_to: date) -> dto.RecommendationStats:
        start = datetime.combine(date_from, time.min, tzinfo=UTC)
        end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=UTC)
        logs = (
            await self._s.scalars(
                select(RecommendationLog)
                .where(RecommendationLog.created_at >= start, RecommendationLog.created_at < end)
                .order_by(RecommendationLog.created_at)
                .limit(MAX_ROWS)
            )
        ).all()
        generated = len(logs)
        saved = 0
        if logs:
            saved_rows = await self._s.scalars(
                select(Course.recommendation_log_id)
                .where(Course.recommendation_log_id.in_([lg.id for lg in logs]))
                .where(Course.status.in_(["saved", "shared", "completed"]))
                .distinct()
            )
            saved = len(saved_rows.all())

        regions = {i: s for i, s in (await self._s.execute(select(Region.id, Region.slug))).all()}
        purposes = {i: c for i, c in (await self._s.execute(select(Purpose.id, Purpose.code))).all()}
        heat: Counter[tuple[str, str]] = Counter()
        budgets: list[int] = []
        per_person: list[float] = []
        slot_empty = rerolls = 0
        last_seen: dict[tuple[object, ...], datetime] = {}
        for lg in logs:
            heat[(regions.get(lg.region_id or -1, "?"), purposes.get(lg.purpose_id or -1, "?"))] += 1
            req = lg.request or {}
            if isinstance(req.get("budget_total"), int):
                budgets.append(req["budget_total"])
                per_person.append(req["budget_total"] / max(1, int(req.get("party_size") or 1)))
            if any(w.get("code") == "SLOT_EMPTY" for w in lg.warnings or []):
                slot_empty += 1
            # re-roll: the same user (or anonymous input) asks again for the same region × purpose
            key = (
                lg.user_id or f"anon:{req.get('budget_total')}:{req.get('party_size')}",
                lg.region_id,
                lg.purpose_id,
            )
            created = as_utc(lg.created_at) or start
            if key in last_seen and created - last_seen[key] <= REROLL_WINDOW:
                rerolls += 1
            last_seen[key] = created
        latencies = sorted(lg.latency_ms for lg in logs)
        return dto.RecommendationStats(
            date_from=date_from,
            date_to=date_to,
            generated=generated,
            saved=saved,
            save_rate=round(saved / generated, 4) if generated else 0.0,
            reroll_rate=round(rerolls / generated, 4) if generated else 0.0,
            avg_budget_total=round(sum(budgets) / len(budgets), 1) if budgets else None,
            avg_budget_per_person=round(sum(per_person) / len(per_person), 1) if per_person else None,
            slot_empty_rate=round(slot_empty / generated, 4) if generated else 0.0,
            latency_p50_ms=percentile(latencies, 0.5),
            latency_p95_ms=percentile(latencies, 0.95),
            heatmap=[dto.HeatCell(region=r, purpose=p, count=n) for (r, p), n in heat.most_common()],
        )

    async def top_places(self, region: str | None, limit: int) -> dto.TopPlaceList:
        stmt = (
            select(
                Place.public_id,
                Place.name,
                Region.slug,
                Category.code,
                PlaceStats.recommend_count,
                PlaceStats.save_count,
            )
            .join(PlaceStats, PlaceStats.place_id == Place.id)
            .join(Region, Region.id == Place.region_id)
            .join(Category, Category.id == Place.category_id)
            .where(PlaceStats.recommend_count > 0)
            .order_by(PlaceStats.recommend_count.desc(), PlaceStats.save_count.desc())
            .limit(limit)
        )
        if region:
            stmt = stmt.where(Region.slug == region)
        return dto.TopPlaceList(
            items=[
                dto.TopPlace(id=pid, name=name, region=slug, category=code, recommend_count=rc, save_count=sc)
                for pid, name, slug, code, rc, sc in (await self._s.execute(stmt)).all()
            ]
        )
