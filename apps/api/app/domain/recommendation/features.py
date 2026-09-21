"""The 8 place features of doc 06 §3. Every function is pure and returns a value in [0, 1]."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime

from app.domain.models import OpeningPeriod, PlaceCandidate, ScoringParams

MINUTES_PER_DAY = 1440

# peak_fit defaults: role -> [[start_hour, end_hour, value], ...]; overridable via params.peak_curves
DEFAULT_PEAK_CURVES: dict[str, list[list[float]]] = {
    "MEAL": [[11.5, 13.5, 1.0], [17.5, 20.0, 1.0], [11.0, 21.0, 0.7]],
    "CAFE": [[13.0, 18.0, 1.0], [10.0, 21.0, 0.75]],
    "DESSERT": [[13.0, 20.0, 1.0], [11.0, 22.0, 0.7]],
    "ATTRACTION": [[10.0, 18.0, 1.0], [18.0, 21.0, 0.7]],
    "ACTIVITY": [[13.0, 21.0, 1.0], [10.0, 23.0, 0.7]],
    "CULTURE": [[10.0, 18.0, 1.0], [18.0, 20.0, 0.7]],
    "BAR": [[19.0, 23.0, 1.0], [17.0, 26.0, 0.7]],
    "NIGHTVIEW": [[19.0, 23.5, 1.0], [18.0, 25.0, 0.7]],
}
PEAK_FLOOR = 0.3


def clip01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


# --- 3.1 budget -----------------------------------------------------------------------------


def _gauss(u: float, target: float, sigma: float) -> float:
    return math.exp(-((u - target) ** 2) / (2 * sigma * sigma))


def budget_fit(
    price: int | None, is_free: bool, slot_budget: float, slot_share: float, params: ScoringParams
) -> float:
    if is_free or not price:
        small = slot_share <= params.free_share_threshold
        return params.free_score_small_share if small else params.free_score_other
    if slot_budget <= 0:
        return 0.0
    u = price / slot_budget
    target, sigma = params.budget_target_util, params.budget_sigma
    if u <= 1.0:
        s = sigma * params.budget_sigma_low_factor if u < target else sigma
        return _gauss(u, target, s)
    if u <= params.price_cap_ratio:
        return max(0.0, _gauss(1.0, target, sigma) - params.budget_over_slope * (u - 1.0))
    return 0.0


# --- distance -------------------------------------------------------------------------------


def distance_fit(distance_m: float, scale_m: float) -> float:
    return clip01(math.exp(-max(0.0, distance_m) / max(1.0, scale_m)))


# --- 3.2 rating -----------------------------------------------------------------------------


def bayesian_rating(avg: float | None, count: int, prior_mean: float, m: float) -> float:
    if avg is None or count <= 0:
        return prior_mean
    return (count * avg + m * prior_mean) / (count + m)


def rating_fit(bayes_rating: float) -> float:
    return clip01((bayes_rating - 3.0) / 2.0)


def zscore_weighted_rating(
    sources: Sequence[tuple[float, int, float, float]], target_mean: float, target_std: float
) -> float | None:
    """Combine per-provider ratings (avg, count, provider_mean, provider_std) on a common scale."""
    total = sum(c for _, c, _, _ in sources)
    if total <= 0:
        return None
    z = sum(((avg - mu) / sd if sd > 0 else 0.0) * c for avg, c, mu, sd in sources) / total
    return max(0.0, min(5.0, target_mean + z * target_std))


# --- 3.3 sentiment --------------------------------------------------------------------------


def recency_weighted_sentiment(
    items: Iterable[tuple[float, datetime]], now: datetime, half_life_days: float = 180.0
) -> float | None:
    num = den = 0.0
    for score, written_at in items:
        age = max(0.0, (now - written_at).total_seconds() / 86400.0)
        w = 0.5 ** (age / half_life_days)
        num += w * score
        den += w
    return num / den if den > 0 else None


def sentiment_fit(
    score: float | None, count: int, aspects: Mapping[str, float] | None, params: ScoringParams
) -> float:
    if score is None or count <= 0:
        return 0.5
    s = max(-1.0, min(1.0, score))
    weights = params.aspect_weights
    if aspects and weights:
        den = sum(w for k, w in weights.items() if k in aspects and w > 0)
        if den > 0:
            a = sum((2 * aspects[k] - 1) * w for k, w in weights.items() if k in aspects and w > 0) / den
            s = (1 - params.aspect_blend) * s + params.aspect_blend * a
    shrunk = s * count / (count + params.sentiment_shrink_n)
    return clip01((shrunk + 1) / 2)


# --- congestion -----------------------------------------------------------------------------


def congestion_at(place: PlaceCandidate, when: datetime) -> float | None:
    return place.popular_times.get((when.weekday(), when.hour))


def congestion_fit(congestion: float | None) -> float:
    return 0.5 if congestion is None else clip01(1.0 - congestion)


# --- 3.4 time fit / opening hours -----------------------------------------------------------


def _in_break(p: OpeningPeriod, minute: int) -> bool:
    if p.break_start_min is None or p.break_end_min is None:
        return False
    return p.break_start_min <= minute < p.break_end_min


def minutes_until_close(hours: Sequence[OpeningPeriod], when: datetime) -> float | None:
    """Minutes left until the place closes (or its break starts). None = closed now.

    No opening-hour data at all means "always open" (parks, streets) → +inf.
    """
    if not hours:
        return math.inf
    dow, minute = when.weekday(), when.hour * 60 + when.minute
    for p in hours:
        if p.is_closed:
            continue
        if p.dow == dow:
            m = minute
        elif p.dow == (dow - 1) % 7 and p.close_min > MINUTES_PER_DAY:
            m = minute + MINUTES_PER_DAY
        else:
            continue
        if not (p.open_min <= m < p.close_min) or _in_break(p, m):
            continue
        if p.break_start_min is not None and m < p.break_start_min:
            return float(p.break_start_min - m)
        return float(p.close_min - m)
    return None


def is_open(hours: Sequence[OpeningPeriod], when: datetime, stay_min: int = 0) -> bool:
    left = minutes_until_close(hours, when)
    return left is not None and left >= stay_min


def peak_fit(role: str, when: datetime, curves: Mapping[str, list[list[float]]] | None = None) -> float:
    windows = (curves or {}).get(role) or DEFAULT_PEAK_CURVES.get(role)
    if not windows:
        return 0.7
    hour = when.hour + when.minute / 60.0
    best = PEAK_FLOOR
    for start, end, value in windows:
        if start <= hour < end or start <= hour + 24 < end:
            best = max(best, value)
    return clip01(best)


def time_fit(place: PlaceCandidate, arrive: datetime, stay_min: int, params: ScoringParams) -> float:
    left = minutes_until_close(place.opening_hours, arrive)
    if left is None:
        return 0.0
    open_margin = 1.0 if math.isinf(left) else clip01((left - stay_min) / 60.0)
    return clip01(0.6 * open_margin + 0.4 * peak_fit(place.course_role, arrive, params.peak_curves))


# --- 3.5 preference / purpose ---------------------------------------------------------------


def cosine(a: Mapping[str, float], b: Mapping[str, float]) -> float:
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    dot = sum(v * b.get(k, 0.0) for k, v in a.items())
    return dot / (na * nb)


def preference_fit(
    place: PlaceCandidate,
    liked_tags: Sequence[str],
    disliked_tags: Sequence[str],
    category_weights: Mapping[str, float],
    params: ScoringParams,
    now: datetime | None = None,
) -> float:
    user: dict[str, float] = {f"tag:{t}": 1.0 for t in liked_tags}
    user.update({f"tag:{t}": -1.0 for t in disliked_tags})
    user.update({f"cat:{c}": w for c, w in category_weights.items()})
    if not user:  # cold start → purpose prior → 0.5
        user = {f"tag:{t}": w for t, w in params.preference_prior.items()}
    if not user:
        base = 0.5
    else:
        vec = {f"tag:{t}": w for t, w in place.tags.items()}
        vec[f"cat:{place.category_code}"] = 1.0
        vec[f"cat:{place.top_category}"] = 1.0
        base = (cosine(user, vec) + 1) / 2
    if place.is_overexposed:
        base -= params.explore_penalty
    if now and place.approved_at and (now - place.approved_at).days <= params.new_place_days:
        base += params.explore_bonus
    return clip01(base)


def purpose_fit(place_tags: Mapping[str, float], affinity: Mapping[str, float]) -> float:
    den = sum(w for t, w in place_tags.items() if t in affinity and w > 0)
    if den <= 0:
        return 0.5
    x = sum(affinity[t] * w for t, w in place_tags.items() if t in affinity and w > 0) / den
    return clip01((max(-1.0, min(1.0, x)) + 1) / 2)
