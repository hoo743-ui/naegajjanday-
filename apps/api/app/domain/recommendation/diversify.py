"""Alternatives (doc 06 §5): labeled variant profiles + MMR so alternatives overlap < 50% in places."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace
from typing import Any

from app.domain.models import FEATURE_KEYS, ScoringParams, ScoringProfile

Key = frozenset[tuple[bool, int]]

PRIMARY_LABEL = "추천 코스"
FALLBACK_LABEL = "다른 분위기 코스"

# Used when `scoring_profile.params.variants` is not set. weight_mult twists the base weights,
# params overrides ScoringParams fields.
DEFAULT_VARIANTS: list[dict[str, Any]] = [
    {
        "label": "가성비 코스",
        "weight_mult": {"budget": 1.5, "rating": 0.9},
        "params": {"budget_target_util": 0.6, "utilization_lo": 0.5, "utilization_hi": 0.8},
    },
    {
        # Was "평점 우선 코스" on rating × 1.8: there are no ratings in the data (every place scores the same
        # neutral value), so the twist did nothing and the label promised what we do not have. `curated` is
        # the selection signal we do have: vouched for by a public body, or measurably visited.
        "label": "검증된 곳 코스",
        "weight_mult": {"curated": 1.8, "budget": 0.7},
        "params": {},
    },
    {
        "label": "덜 걷는 코스",
        "weight_mult": {"distance": 2.5},
        "params": {"lambda_travel": 0.045, "distance_scale_m": 500.0},
    },
]


def variant_profile(base: ScoringProfile, variant: dict[str, Any]) -> ScoringProfile:
    mult = variant.get("weight_mult") or {}
    weights = {k: base.weights.get(k, 0.0) * float(mult.get(k, 1.0)) for k in FEATURE_KEYS}
    known = set(ScoringParams.__dataclass_fields__)
    overrides = {k: v for k, v in (variant.get("params") or {}).items() if k in known}
    return replace(base, weights=weights, params=replace(base.params, **overrides))


def overlap(a: Key, b: Key) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / max(len(a), len(b))


def mmr_pick[T](
    pool: Sequence[T],
    selected: Sequence[Key],
    *,
    key: Callable[[T], Key],
    relevance: Callable[[T], float],
    lam: float,
    max_overlap: float,
) -> T | None:
    """argmax λ·rel − (1−λ)·max_sim among items that stay below `max_overlap` with everything selected.

    If nothing qualifies (tiny regions), falls back to the least-overlapping non-identical item.
    """
    best: tuple[float, T] | None = None
    loosest: tuple[float, float, T] | None = None
    for item in pool:
        k = key(item)
        sim = max((overlap(k, s) for s in selected), default=0.0)
        if sim >= 1.0:
            continue
        rel = relevance(item)
        if sim < max_overlap:
            value = lam * rel - (1 - lam) * sim
            if best is None or value > best[0]:
                best = (value, item)
        elif loosest is None or (sim, -rel) < (loosest[0], loosest[1]):
            loosest = (sim, -rel, item)
    if best is not None:
        return best[1]
    return loosest[2] if loosest is not None else None
