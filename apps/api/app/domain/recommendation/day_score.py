"""Best Day objective (docs/29): score the whole day, not the sum of short hops.

v1 (`composer.objective`) = mean place score − 0.015 · minutes per stop − overrun + small category bonus.
One extra minute of average walking cost as much as a clearly better place: the nearest bundle always won.

v2 keeps the place score (purpose · taste · quality · budget · time fit, `PlaceScorer`) and adds what only
the whole day can show:

    DayScore = mean S                                   place quality, purpose, taste, budget and time fit
             + experience_diversity · kinds / stops      a meal, a café, something to do, a view …
             + destination · (standout + mean)/2         what the area is known for, vouched for, visited
             + reliability · measured share              prices and places we actually know
             − Σ travel_curve(leg / comfort)             non-linear: 20→25 min is little, 20→60 is a lot
             − travel_ratio · max(0, travel/day − free)  a day spent on the road is not a day out
             − overrun · over / budget                   (never: budget is a hard limit, kept for replans)
             − budget_risk · max(0, spent + u·estimated − budget) / budget
             − schedule_risk · share of stops leaving just before closing
             − repetition · repeated kinds / stops       four cafés is not a date
             − area_concentration (a long day in one block) + exploration (a few blocks, all of them good)
             + utilization when the budget is used well

Every coefficient lives in `DEFAULT_DAY_WEIGHTS` and can be overridden per purpose through
`scoring_profile.params.day_score`. Nothing here is shown to the user as a number.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import timedelta
from itertools import pairwise
from typing import TYPE_CHECKING

from app.domain.models import PlaceCandidate, RequestContext, ScoringParams, Template
from app.domain.recommendation.features import is_open
from app.domain.routing.travel_time import haversine_m

if TYPE_CHECKING:
    from app.domain.recommendation.composer import Partial, PlannedStop

DEFAULT_DAY_WEIGHTS: dict[str, float] = {
    "experience_diversity": 0.10,
    "destination": 0.06,
    "reliability": 0.03,
    "travel": 1.0,
    "travel_ratio": 1.2,
    "travel_ratio_free": 0.15,
    "budget_risk": 0.3,
    "price_uncertainty": 0.15,  # an estimated (category average) price may be this much off
    "schedule_risk": 0.04,
    "schedule_margin_min": 20.0,
    "repetition": 0.06,
    "area_concentration": 0.03,
    "area_cell_m": 500.0,
    "exploration": 0.02,
    "exploration_cell_m": 800.0,
    "exploration_floor": 0.62,  # exploring only counts when every stop is good on its own
}

# move style (docs/29 §10): how far a person is happy to go for something better
MOVE_STYLES: dict[str, dict[str, float]] = {
    "local": {"comfort": 0.75, "tiers": 0.0},
    "balanced": {"comfort": 1.0, "tiers": 2.0},
    "explorer": {"comfort": 1.4, "tiers": 3.0},
}
EXPLORER_EXTRA_TIER = 4.0  # an explorer's last ring, × the core radius
SHORT_DAY_MIN = 180  # a short meeting: one ring less, and travel matters more

# kinds of experience a day is made of (docs/29 §6)
DINING, CAFE, ACTIVITY, CULTURE, WALK, VIEW, NIGHT, SHOPPING = (
    "DINING", "CAFE", "ACTIVITY", "CULTURE", "WALK", "VIEW", "NIGHT", "SHOPPING",
)  # fmt: skip
_ROLE_KIND = {
    "MEAL": DINING,
    "CAFE": CAFE,
    "DESSERT": CAFE,
    "BAR": NIGHT,
    "ACTIVITY": ACTIVITY,
    "CULTURE": CULTURE,
    "NIGHTVIEW": VIEW,
}
_ATTRACTION_KIND = {"attraction.park": WALK, "attraction.street": WALK, "attraction.market": SHOPPING}
REPEATABLE = {DINING: 2}  # lunch and dinner are two meals, not a repetition

REASONS = (
    "PURPOSE_MATCH",
    "LOCAL_SIGNIFICANCE",
    "WORTH_THE_TRIP",
    "UNIQUE_EXPERIENCE",
    "USER_PREFERENCE",
    "HIGH_PLACE_QUALITY",
    "BUDGET_FIT",
    "DIVERSITY",
    "ROUTE_BALANCE",
)
MAX_REASONS = 4


def weights(params: ScoringParams) -> dict[str, float]:
    return {**DEFAULT_DAY_WEIGHTS, **{k: float(v) for k, v in (params.day_score or {}).items()}}


def experience_kind(place: PlaceCandidate) -> str | None:
    if place.course_role == "ATTRACTION":
        return next((k for code, k in _ATTRACTION_KIND.items() if place.category_code.startswith(code)), VIEW)
    return _ROLE_KIND.get(place.course_role)


def comfort_min(params: ScoringParams, ctx: RequestContext) -> float:
    style = MOVE_STYLES.get(ctx.move_style, MOVE_STYLES["balanced"])
    short = 0.8 if ctx.duration_min and ctx.duration_min <= SHORT_DAY_MIN else 1.0
    return params.comfort_leg_min(ctx.transport) * style["comfort"] * short


def reach_tiers(params: ScoringParams, ctx: RequestContext) -> list[float]:
    """Rings around the core area to look into, as multiples of its radius (docs/29 §2)."""
    style = MOVE_STYLES.get(ctx.move_style, MOVE_STYLES["balanced"])
    tiers = list(params.reach_tiers)
    if ctx.move_style == "explorer":
        tiers.append(EXPLORER_EXTRA_TIER)
    count = int(style["tiers"])
    if ctx.duration_min and ctx.duration_min <= SHORT_DAY_MIN:  # CASE C: a short day stays closer
        count -= 1
    return tiers[: max(0, count)]


def leg_penalty(minutes: float, comfort: float, curve: Sequence[Sequence[float]]) -> float:
    """Piecewise-linear in `minutes / comfort`; past the last knot the last slope continues."""
    x = max(0.0, minutes) / max(1.0, comfort)
    knots = [(float(a), float(b)) for a, b in curve] or [(0.0, 0.0), (1.0, 0.0)]
    for (x0, y0), (x1, y1) in pairwise(knots):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / max(1e-9, x1 - x0)
    (xa, ya), (xb, yb) = knots[-2], knots[-1]
    return yb + (yb - ya) / max(1e-9, xb - xa) * (x - xb)


def _cells(stops: Sequence[PlannedStop], cell_m: float) -> set[tuple[int, int]]:
    d_lat = cell_m / 111_000
    out = set()
    for s in stops:
        d_lng = d_lat / max(0.2, math.cos(math.radians(s.place.lat)))
        out.add((math.floor(s.place.lat / d_lat), math.floor(s.place.lng / d_lng)))
    return out


def _tight_close(s: PlannedStop, margin_min: float) -> bool:
    """Leaves only minutes before the door closes: one late bus and the visit is gone."""
    if not s.place.opening_hours:
        return False
    stay = int((s.leave - s.arrive).total_seconds() // 60)
    return not is_open(s.place.opening_hours, s.arrive, stay + int(margin_min))


def breakdown(
    p: Partial, ctx: RequestContext, params: ScoringParams, *, final: bool = False
) -> dict[str, float]:
    """Each term of the day score, signed as it enters the total."""
    n = len(p.stops)
    if n == 0:
        return {}
    w = weights(params)
    b = ctx.budget_per_person
    stops = p.stops
    kinds = [experience_kind(s.place) for s in stops]
    known = [k for k in kinds if k]
    out: dict[str, float] = {"place": p.score_sum / n}
    out["experience_diversity"] = w["experience_diversity"] * len(set(known)) / n
    destination = [s.score.breakdown.get("curated", 0.0) for s in stops]
    out["destination"] = w["destination"] * (max(destination) + sum(destination) / n) / 2
    reliable = sum(
        1 for s in stops if s.place.is_free or not s.place.price_is_estimated or s.place.is_curated
    )
    out["reliability"] = w["reliability"] * reliable / n
    comfort = comfort_min(params, ctx)
    # every leg counts, the first one too: people start at the station of the area they picked and walk it
    legs = [s.leg.minutes for s in stops]
    # a day total, not a per-stop average: one 35-minute walk is a real cost however many stops there are
    out["travel"] = -w["travel"] * sum(leg_penalty(m, comfort, params.travel_curve) for m in legs)
    if b > 0:
        out["overrun"] = -params.lambda_overrun * max(0.0, p.spent - b) / b
        estimated = sum(s.place.price for s in stops if s.place.price_is_estimated and not s.place.is_free)
        worst = p.spent + w["price_uncertainty"] * estimated
        out["budget_risk"] = -w["budget_risk"] * max(0.0, worst - b) / b
    out["schedule_risk"] = (
        -w["schedule_risk"] * sum(1 for s in stops if _tight_close(s, w["schedule_margin_min"])) / n
    )
    counts = Counter(known)
    liked_tops = {code for code, v in ctx.category_weights.items() if v > 0}
    repeated = 0
    for kind, c in counts.items():
        allowed = REPEATABLE.get(kind, 1)
        # the user said they like this kind of place: a second one is what they asked for
        if any(s.place.top_category in liked_tops for s, k in zip(stops, kinds, strict=True) if k == kind):
            allowed += 1
        repeated += max(0, c - allowed)
    out["repetition"] = -w["repetition"] * repeated / n
    if n >= 4 and len(_cells(stops, w["area_cell_m"])) == 1:
        out["area_concentration"] = -w["area_concentration"]
    if min(s.score.total for s in stops) >= w["exploration_floor"]:
        spread = len(_cells(stops, w["exploration_cell_m"])) - 1
        out["exploration"] = w["exploration"] * min(spread, 2) / 2
    if final:
        day_min = ctx.duration_min or (stops[-1].leave - ctx.start_at) / timedelta(minutes=1)
        ratio = sum(legs) / max(60.0, day_min)
        out["travel_ratio"] = -w["travel_ratio"] * max(0.0, ratio - w["travel_ratio_free"])
        if b > 0 and params.utilization_lo <= p.spent / b <= params.utilization_hi:
            out["utilization"] = params.utilization_bonus
    return out


def day_objective(p: Partial, ctx: RequestContext, params: ScoringParams, *, final: bool = False) -> float:
    return sum(breakdown(p, ctx, params, final=final).values())


def reason_codes(
    stop: PlannedStop, stops: Sequence[PlannedStop], ctx: RequestContext, params: ScoringParams
) -> list[str]:
    """Why this place, as codes the UI can explain (docs/29 §15). Strongest first, at most four."""
    f: Mapping[str, float] = stop.score.breakdown
    place = stop.place
    kind = experience_kind(place)
    kinds = [experience_kind(s.place) for s in stops]
    unique = kind is not None and kinds.count(kind) == 1
    found: set[str] = set()
    if f.get("purpose_fit", 0.0) >= 0.6:
        found.add("PURPOSE_MATCH")
    if place.local_score > 0 or place.id in ctx.landmark_ids:
        found.add("LOCAL_SIGNIFICANCE")
    if (place.is_event, place.id) in ctx.ring_keys:
        found.add("WORTH_THE_TRIP")
    if unique and kind in (ACTIVITY, CULTURE, VIEW, WALK):
        found.add("UNIQUE_EXPERIENCE")
    elif unique and len(stops) >= 3:
        found.add("DIVERSITY")
    if ctx.liked_tags and any(place.tags.get(t, 0.0) >= 0.5 for t in ctx.liked_tags):
        found.add("USER_PREFERENCE")
    if f.get("curated", 0.0) >= 0.6 or (place.rating_count > 0 and f.get("rating", 0.0) >= 0.75):
        found.add("HIGH_PLACE_QUALITY")
    if f.get("budget", 0.0) >= 0.75:
        found.add("BUDGET_FIT")
    first = stops[0] is stop if stops else True
    if not first and stop.leg.minutes <= comfort_min(params, ctx):
        found.add("ROUTE_BALANCE")
    return [r for r in REASONS if r in found][:MAX_REASONS]


STRUCTURE_FILL = ("CULTURE", "ACTIVITY")  # what a day with a repeated kind is offered instead


def structure_alternative(template: Template, fill_order: Sequence[str] = ()) -> Template | None:
    """The template with its first repeated kind of experience (beyond what may repeat) replaced by a
    kind the day does not have yet: café + dessert café → café + an exhibition. None when nothing repeats
    or nothing is missing. Budget share and timing of the slot stay as they are."""
    roles = {s.course_role for s in template.slots}
    order = [*fill_order, *(r for r in STRUCTURE_FILL if r not in fill_order)]
    fill = next((r for r in order if r not in roles), None)
    if fill is None:
        return None
    seen: Counter[str] = Counter()
    for i, slot in enumerate(template.slots):
        kind = _ROLE_KIND.get(slot.course_role)
        if kind is None:
            continue
        seen[kind] += 1
        if seen[kind] > REPEATABLE.get(kind, 1):
            slots = list(template.slots)
            slots[i] = replace(slot, course_role=fill)
            return replace(template, slots=tuple(slots))
    return None


def area_fit(distance_from_centre_m: float, core_radius_m: float, falloff_m: float) -> float:
    """v2's place-level distance feature: inside the area = 1, then a gentle fall (not a wall)."""
    beyond = max(0.0, distance_from_centre_m - max(0.0, core_radius_m))
    return math.exp(-beyond / max(1.0, falloff_m))


def distance_from_centre(place: PlaceCandidate, ctx: RequestContext) -> float:
    return haversine_m(ctx.origin, place.point)
