"""Batch refresh of `place_stats.bayes_rating` (doc 06 §3.2): prior C = region × category mean."""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import ScoringParams
from app.domain.recommendation.features import bayesian_rating
from app.infra.db.models import Place, PlaceStats


async def refresh_region_stats(session: AsyncSession, region_id: int, bayes_m: float | None = None) -> int:
    defaults = ScoringParams()
    m = bayes_m if bayes_m is not None else defaults.bayes_m
    rows = (
        await session.execute(
            select(PlaceStats, Place.category_id)
            .join(Place, Place.id == PlaceStats.place_id)
            .where(Place.region_id == region_id)
        )
    ).all()
    total: dict[int, float] = defaultdict(float)
    weight: dict[int, int] = defaultdict(int)
    for stats, category_id in rows:
        if stats.rating_avg is not None and stats.rating_count > 0:
            total[category_id] += stats.rating_avg * stats.rating_count
            weight[category_id] += stats.rating_count
    for stats, category_id in rows:
        prior = (
            total[category_id] / weight[category_id] if weight[category_id] else defaults.bayes_prior_default
        )
        stats.bayes_rating = round(bayesian_rating(stats.rating_avg, stats.rating_count, prior, m), 4)
    return len(rows)
