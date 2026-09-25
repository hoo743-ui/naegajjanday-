"""Course composition by beam search (doc 06 §4–§5).

J(course) = mean S − λ_t·(travel_min / slots) − λ_o·max(0, Σprice − b)/b + δ·diversity + ρ·util_bonus
subject to Σprice ≤ b (budget_tolerance), leg ≤ T_max(mode), arrival ∈ opening hours ∩ slot window, no dup.
sub-category. Money saved by earlier slots is carried over into the next slot's b_s before re-scoring.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.domain.models import GeoPoint, PlaceCandidate, RequestContext, ScoringParams
from app.domain.recommendation import day_score
from app.domain.recommendation.budget import SlotBudget, effective_budget
from app.domain.recommendation.features import congestion_at, is_open
from app.domain.recommendation.scorer import PlaceScorer, Score, ScoreInput
from app.domain.routing.travel_time import HaversineEstimator, Leg

MIN_OPEN_BUFFER_MIN = 30
FIXED_STAY_MIN = 120  # a show (film, ball game) — its length does not follow the requested window
WINDOW_GRACE_MIN = 15  # a course may end this much after the requested window (v2)
ON_PLAN_SEATS_DIVISOR = 4  # a quarter of the beam is kept for partials that have not overspent
MIN_CATEGORIES_IN_TOP_K = 4  # a slot's shortlist spans at least this many categories when the pool allows


@dataclass(frozen=True, slots=True)
class PlannedStop:
    place: PlaceCandidate
    sb: SlotBudget
    arrive: datetime
    leave: datetime
    leg: Leg
    score: Score
    eff_budget: float
    congestion: float | None


@dataclass(frozen=True, slots=True)
class Partial:
    stops: tuple[PlannedStop, ...]
    spent: float
    planned: float
    travel_min: float
    distance_m: float
    clock: datetime
    last_point: GeoPoint
    score_sum: float

    @property
    def keys(self) -> frozenset[tuple[bool, int]]:
        return frozenset((s.place.is_event, s.place.id) for s in self.stops)


def stay_minutes(place: PlaceCandidate, stay_scale: float) -> int:
    """A stay stretched or shrunk to the requested window — except a show: a film (130) or a ball game (180)
    lasts as long as it lasts, so a place staying FIXED_STAY_MIN or more keeps its length. A short window
    then simply has no room for it (the window check in `extend` drops it) instead of a 65-minute film."""
    if place.default_stay_min >= FIXED_STAY_MIN:
        return place.default_stay_min
    return max(15, round(place.default_stay_min * stay_scale))


def slot_window_ok(sb: SlotBudget, day0: datetime, arrive: datetime, max_wait: int) -> datetime | None:
    """Apply the slot's [earliest_start, latest_start]; returns the (possibly delayed) start time."""
    slot = sb.slot
    minute = (arrive - day0).total_seconds() / 60.0
    earliest, latest = slot.earliest_start_min, slot.latest_start_min
    if earliest is not None and latest is not None and latest < earliest:
        latest += 1440
    if earliest is not None and minute < earliest:
        if earliest - minute > max_wait:
            return None
        arrive = day0 + timedelta(minutes=earliest)
        minute = earliest
    if latest is not None and minute > latest:
        return None
    return arrive


def objective(
    p: Partial,
    budget_per_person: float,
    params: ScoringParams,
    *,
    final: bool = False,
    ctx: RequestContext | None = None,
) -> float:
    """v1: J above. v2 (docs/29): the whole day (`day_score`) — pass the request context to get it."""
    if ctx is not None and ctx.is_v2:
        return day_score.day_objective(p, ctx, params, final=final)
    n = len(p.stops)
    if n == 0:
        return 0.0
    j = p.score_sum / n
    j -= params.lambda_travel * (p.travel_min / n)
    if budget_per_person > 0:
        j -= params.lambda_overrun * max(0.0, p.spent - budget_per_person) / budget_per_person
    j += params.diversity_bonus * len({s.place.top_category for s in p.stops}) / n
    if final and budget_per_person > 0:
        util = p.spent / budget_per_person
        if params.utilization_lo <= util <= params.utilization_hi:
            j += params.utilization_bonus
    return j


class CourseComposer:
    def __init__(
        self,
        scorer: PlaceScorer,
        ctx: RequestContext,
        estimator: HaversineEstimator | None = None,
        stay_scale: float = 1.0,
    ) -> None:
        self._scorer = scorer
        self._ctx = ctx
        self._params = scorer.profile.params
        self._est = estimator or HaversineEstimator()
        self._stay_scale = stay_scale
        self._day0 = ctx.start_at.replace(hour=0, minute=0, second=0, microsecond=0)

    def leg_limit(self) -> float:
        """The longest single leg allowed. v1: a comfort limit used as a wall (20 min on foot).
        v2: only what nobody would do with that mode; anything shorter is priced by the day score."""
        mode = self._ctx.transport
        limit = self._params.hard_leg_min(mode) if self._ctx.is_v2 else self._params.max_leg_min(mode)
        # at night a long walk between two places is not a stroll: the night condition caps it (walk only)
        return min(limit, self._ctx.leg_cap_min) if self._ctx.leg_cap_min and mode == "walk" else limit

    def empty(self) -> Partial:
        c = self._ctx
        return Partial((), 0.0, 0.0, 0.0, 0.0, c.start_at, c.origin, 0.0)

    def rank(
        self, cands: Sequence[PlaceCandidate], sb: SlotBudget, est_arrive: datetime
    ) -> list[PlaceCandidate]:
        """top-K(slot) by S, measured from the origin with the un-carried slot budget."""
        scored = []
        for p in cands:
            if self._ctx.is_v2:  # v2: how far from the area's centre, straight (the travel is a day term)
                distance = day_score.distance_from_centre(p, self._ctx)
            else:
                distance = self._est.estimate(self._ctx.origin, p.point, self._ctx.transport).distance_m
            x = ScoreInput(p, sb.budget, sb.share, distance, est_arrive, stay_minutes(p, self._stay_scale))
            scored.append((self._scorer.score(x).total, p))
        scored.sort(key=lambda t: (-t[0], t[1].id))
        # A course never repeats a category (see `extend`). If one category owns the whole top-K — the
        # date profile loves 양식 — a second slot of the same role (lunch + dinner) has nothing left to
        # pick once the first took that category. Cap each category's seats so the list stays mixed.
        top_k = self._params.top_k
        per_category = max(2, math.ceil(top_k / MIN_CATEGORIES_IN_TOP_K))
        seats: dict[str, int] = {}
        picked: list[PlaceCandidate] = []
        for _, p in scored:
            if seats.get(p.category_code, 0) >= per_category:
                continue
            seats[p.category_code] = seats.get(p.category_code, 0) + 1
            picked.append(p)
            if len(picked) == top_k:
                break
        return picked

    def extend(
        self, partial: Partial, place: PlaceCandidate, sb: SlotBudget, *, strict: bool = True
    ) -> Partial | None:
        ctx, params = self._ctx, self._params
        # a stop the user pinned was in their course already: two of one kind or a longer walk is their call,
        # the budget and the hours are not
        pinned = bool(ctx.kept_places) and (place.is_event, place.id) in ctx.kept_keys
        if strict:
            if (place.is_event, place.id) in partial.keys:
                return None
            if not pinned and any(s.place.category_code == place.category_code for s in partial.stops):
                return None
            if partial.spent + place.price > params.budget_tolerance * ctx.budget_per_person:
                return None
        leg = self._est.estimate(partial.last_point, place.point, ctx.transport)
        if strict and partial.stops and not pinned and leg.minutes > self.leg_limit():
            return None
        arrive = partial.clock + timedelta(minutes=round(leg.minutes))
        windowed = slot_window_ok(sb, self._day0, arrive, params.max_wait_min)
        if windowed is None:
            if strict:
                return None
        else:
            arrive = windowed
        # the stretch exists to reach a gated slot (dinner from 17:00), not to make that slot overrun the
        # window → a gated slot keeps at most its normal length
        gated = sb.slot.earliest_start_min is not None
        stay = stay_minutes(place, min(self._stay_scale, 1.0) if gated else self._stay_scale)
        if strict and not is_open(place.opening_hours, arrive, min(stay, MIN_OPEN_BUFFER_MIN)):
            return None
        eff = effective_budget(sb.budget, partial.planned - partial.spent)
        # v1 scores the hop from the previous stop; v2 scores the place's distance from the area's centre and
        # leaves the hop to the day score (the travel curve), so distance is not counted twice
        distance = day_score.distance_from_centre(place, ctx) if ctx.is_v2 else leg.distance_m
        score = self._scorer.score(ScoreInput(place, eff, sb.share, distance, arrive, stay))
        leave = arrive + timedelta(minutes=stay)
        # v2: longer legs are allowed, so the meeting window must be checked, not assumed — the time the user
        # gave is a hard limit (docs/29 §1). v1 fitted the window by trimming slots and kept no such check.
        if (
            strict
            and ctx.is_v2
            and ctx.duration_min
            and leave > ctx.start_at + timedelta(minutes=ctx.duration_min + WINDOW_GRACE_MIN)
        ):
            return None
        stop = PlannedStop(place, sb, arrive, leave, leg, score, eff, congestion_at(place, arrive))
        return Partial(
            stops=(*partial.stops, stop),
            spent=partial.spent + place.price,
            planned=partial.planned + sb.budget,
            travel_min=partial.travel_min + round(leg.minutes),
            distance_m=partial.distance_m + leg.distance_m,
            clock=leave,
            last_point=place.point,
            score_sum=partial.score_sum + score.total,
        )

    def search(
        self, slot_budgets: Sequence[SlotBudget], ranked: Mapping[int, Sequence[PlaceCandidate]]
    ) -> tuple[list[Partial], list[int]]:
        """Returns (final beam sorted by J desc, positions of slots that could not be filled)."""
        b = self._ctx.budget_per_person
        ranked = self._reachable(slot_budgets, ranked)
        beam: list[Partial] = [self.empty()]
        unfilled: list[int] = []
        for sb in slot_budgets:
            nxt: list[Partial] = []
            for partial in beam:
                for place in ranked.get(sb.slot.position, ()):
                    grown = self.extend(partial, place, sb)
                    if grown is not None:
                        nxt.append(grown)
            if not nxt:
                unfilled.append(sb.slot.position)
                continue
            nxt.sort(key=lambda p: -objective(p, b, self._params, ctx=self._ctx))
            beam = self._trim(nxt)
        finals = [p for p in beam if p.stops]
        finals.sort(key=lambda p: -objective(p, b, self._params, final=True, ctx=self._ctx))
        return finals, unfilled

    def _reachable(
        self, slot_budgets: Sequence[SlotBudget], ranked: Mapping[int, Sequence[PlaceCandidate]]
    ) -> dict[int, Sequence[PlaceCandidate]]:
        """Keeps, slot by slot from the back, only the places from which a place of the NEXT slot can be
        reached within the longest leg allowed. The beam fills one slot at a time and never looked ahead:
        on foot in a wide district the best-scoring restaurants all stood in one far-off mall, nothing
        was within walking distance of it, and the course came back with a single stop.
        A slot that would be left with nothing keeps everything it had (an honest gap beats no course)."""
        out: dict[int, Sequence[PlaceCandidate]] = dict(ranked)
        limit = self.leg_limit()
        positions = [sb.slot.position for sb in slot_budgets]
        for here, ahead in zip(reversed(positions[:-1]), reversed(positions[1:]), strict=True):
            onward = out.get(ahead) or ()
            if not onward:
                continue
            kept = [
                p
                for p in out.get(here, ())
                if any(
                    q.id != p.id
                    and self._est.estimate(p.point, q.point, self._ctx.transport).minutes <= limit
                    for q in onward
                )
            ]
            if kept:
                out[here] = kept
        return out

    def _trim(self, ranked: list[Partial]) -> list[Partial]:
        """Beam cut that keeps some seats for partials still on their planned budget.

        A pure top-J cut can fill every seat with partials that each overspent a little; none of them
        can then afford the last slot and the evening silently loses its bar. On-plan partials are
        rarely the best so far, but they are the ones that can still finish the template."""
        width = self._params.beam_width
        if len(ranked) <= width:
            return ranked
        reserve = width // ON_PLAN_SEATS_DIVISOR
        early = reserve if self._ctx.is_v2 else 0
        head = ranked[: width - reserve - early]
        tail = ranked[width - reserve - early :]
        on_plan = [p for p in tail if p.spent <= p.planned][:reserve]
        rest = [p for p in tail if p.spent > p.planned][: reserve - len(on_plan)]
        kept = [*head, *on_plan, *rest]
        if early:
            # v2 lets a course go further for a better place; some seats go to the partials that are still
            # early, or a beam full of detours has no time left for the evening's last slot
            ids = {id(p) for p in kept}
            later = sorted((p for p in tail if id(p) not in ids), key=lambda p: p.clock)[:early]
            kept.extend(later)
        return kept

    def replan(
        self, sequence: Sequence[tuple[PlaceCandidate, SlotBudget]], *, strict: bool
    ) -> Partial | None:
        """Re-time and re-score a fixed visiting order (after route optimization, swap or reorder)."""
        partial = self.empty()
        for place, sb in sequence:
            grown = self.extend(partial, place, sb, strict=strict)
            if grown is None:
                return None
            partial = grown
        return partial
