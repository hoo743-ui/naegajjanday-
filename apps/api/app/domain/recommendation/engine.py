"""Pipeline orchestration (doc 06 §0): template → budgets → candidates → scoring → beam search →
route optimization → diversified alternatives. Deterministic; no LLM, no DB — data arrives via Protocols."""

from __future__ import annotations

import contextlib
import math
from collections.abc import Sequence
from dataclasses import replace
from datetime import date, datetime, timedelta
from typing import Any, Protocol

from app.domain.models import (
    CourseResult,
    EngineOutput,
    GeoPoint,
    NoCourseError,
    PlaceCandidate,
    RequestContext,
    ScoringProfile,
    StopResult,
    Template,
    TransportMode,
)
from app.domain.recommendation import budget as B
from app.domain.recommendation import day_score
from app.domain.recommendation import features as F
from app.domain.recommendation.candidates import FilterContext, been_places, hard_filter, never_tags
from app.domain.recommendation.composer import (
    MIN_OPEN_BUFFER_MIN,
    CourseComposer,
    Partial,
    objective,
)
from app.domain.recommendation.diversify import (
    DEFAULT_VARIANTS,
    FALLBACK_LABEL,
    PRIMARY_LABEL,
    Key,
    mmr_pick,
    variant_profile,
)
from app.domain.recommendation.familiarity import is_regular, mark_opened
from app.domain.recommendation.scorer import PlaceScorer
from app.domain.recommendation.style import (
    assign_buzz,
    kept_pools,
    wanted_events,
    wanted_places,
    wanted_pools,
)
from app.domain.routing.optimizer import optimize
from app.domain.routing.problem import RouteProblem, Window
from app.domain.routing.travel_time import (
    HaversineEstimator,
    Leg,
    TravelTimeError,
    TravelTimeProvider,
    haversine_m,
)
from app.domain.signature import focus_pools, get_signature_rules, mark_local

NOMINAL_SLOT_MIN = 70  # stay + transfer, only used to scale stays to a requested duration
MIN_STAY_SCALE = 0.5
GATE_MARGIN = 1.1
RESCALE_PASSES = 3
MAX_STAY_SCALE = 1.6  # a whole-day plan lingers; beyond this a "stay" stops being believable
MMR_POOL = 25
WANTED_REACH_M = 4000.0  # how far to look for something the user asked for by name
RECENTER_BEYOND = 0.6  # further than this share of the radius from the centre: plan around it instead
WALK_AREA_M = 1500  # how far apart the stops of a walking course may lie
WALK_CELL_M = 500  # the grid on which the liveliest pocket of a wide district is looked for


class CandidateSource(Protocol):
    async def fetch(
        self, role: str, origin: GeoPoint, radius_m: float, on_date: date, name_words: Sequence[str] = ()
    ) -> list[PlaceCandidate]:
        """Approved places (and, for ATTRACTION/CULTURE, events running on `on_date`) within the radius.
        `name_words`: signs carrying one of these words are wanted even when they are not the nearest."""
        ...


class _MeasuredEstimator(HaversineEstimator):
    """Haversine with selected legs overridden by a real routing API measurement."""

    def __init__(self, measured: dict[tuple[GeoPoint, GeoPoint], Leg]) -> None:
        self._measured = measured

    def estimate(self, a: GeoPoint, b: GeoPoint, mode: TransportMode) -> Leg:
        return self._measured.get((a, b)) or super().estimate(a, b, mode)


class RecommendationEngine:
    def __init__(self, source: CandidateSource, travel_provider: TravelTimeProvider | None = None) -> None:
        self._source = source
        self._travel = travel_provider
        self._est = HaversineEstimator()

    async def generate(
        self, ctx: RequestContext, templates: Sequence[Template], profile: ScoringProfile
    ) -> EngineOutput:
        b = ctx.budget_per_person
        band = B.time_band_for(ctx.start_at, ctx.duration_min)
        template = B.select_template(
            templates, time_band=band, party_size=ctx.party_size, budget_per_person=b
        )
        out = await self._generate_with(ctx, template, profile)
        # v2 (docs/29 §6): a template with the same kind of experience twice (a café, then a dessert café)
        # is compared with the same day where the second one is something the day lacks. Whole days are
        # compared, not slots: the one with the better day score is kept.
        alt = day_score.structure_alternative(template, ctx.structure_fill) if ctx.is_v2 else None
        if alt is not None:
            try:
                other = await self._generate_with(ctx, alt, profile)
            except NoCourseError:
                other = None
            if (
                other is not None
                and _no_worse_filled(other, out)
                and _kept_count(other, ctx) >= _kept_count(out, ctx)
                and other.courses[0].objective > out.courses[0].objective
            ):
                out = other
        # docs/59 #4 · #5: a café lifted to what a café costs, or a late evening's café (shut, or a 24-hour
        # unmanned one), can cost the day its bar. Then the same day without the café is tried, and taken
        # when it has the bar the other lost (dinner → a walk → a drink).
        floors = B.slot_floors()
        closers = floors.yield_to | frozenset(floors.keep_at(ctx.start_at))
        lean = B.without_short(template, b, ctx.include_roles, start_at=ctx.start_at) if ctx.is_v2 else None
        if lean is not None and not _has_role(out, closers):
            try:
                other = await self._generate_with(ctx, lean, profile)
            except NoCourseError:
                other = None
            if (
                other is not None
                and _has_role(other, closers)
                and len(other.courses[0].stops) >= len(out.courses[0].stops)
                and _kept_count(other, ctx) >= _kept_count(out, ctx)
            ):
                out = other
        return out

    async def _generate_with(
        self, ctx: RequestContext, template: Template, profile: ScoringProfile
    ) -> EngineOutput:
        params = profile.params
        b = ctx.budget_per_person
        # a late evening keeps its drink when the others can lend it the slot's minimum (slot_floors.json)
        slot_budgets = B.allocate(template, b, ctx.include_roles, keep=B.slot_floors().keep_at(ctx.start_at))
        # a short meeting window gets fewer stops, not the same stops with every stay cut in half
        start_min = ctx.start_at.hour * 60 + ctx.start_at.minute
        slot_budgets, trimmed = B.fit_to_duration(
            slot_budgets,
            # an open-ended day still ends: about 00:30 at night, or when the company says so
            # ("아이와": 20:30) — only how many stops fit, not a hard window
            ctx.duration_min or B.soft_window(ctx.start_at, ctx.soft_end_min) or B.night_window(ctx.start_at),
            b,
            per_stop_min=B.SLOT_MIN_PER_STOP * ctx.slot_min_scale,  # a relaxed day: fewer, longer stops
            start_min=start_min,
            keep_roles=ctx.keep_roles,
        )

        warnings: list[dict[str, Any]] = []
        pools = await self._collect(ctx, slot_budgets, profile)
        empty = [sb for sb in slot_budgets if not pools[sb.slot.position]]
        for sb in empty:
            if not sb.slot.is_optional:  # optional = "if it fits"; skipping it is not a shortfall
                warnings.append(_slot_empty(sb.slot.position, sb.slot.course_role))
            slot_budgets = B.drop_slot(slot_budgets, sb.slot.position, b)
        if not slot_budgets:
            raise NoCourseError("no candidates for any slot")

        # Scale stays on the slots that can actually be filled. A slot the search cannot place (no
        # museum within walking distance) leaves a hole before a gated slot: the course then reaches
        # dinner hours early and loses it too. With a requested window, drop such slots, rescale and
        # search again — a few passes settle it. Without one this is the single pass it always was.
        role_of = {sb.slot.position: sb.slot.course_role for sb in slot_budgets}
        optional = {sb.slot.position for sb in slot_budgets if sb.slot.is_optional}
        passes = RESCALE_PASSES if ctx.duration_min else 1
        for attempt in range(passes):
            stay_scale = self._stay_scale(ctx, slot_budgets)
            if stay_scale > 1.0:  # longer stays → fewer of them fit the same window
                slot_budgets, more = B.fit_to_duration(
                    slot_budgets,
                    ctx.duration_min,
                    b,
                    per_stop_min=NOMINAL_SLOT_MIN * ctx.slot_min_scale * stay_scale,
                    keep_roles=ctx.keep_roles,
                )
                trimmed += more
                stay_scale = self._stay_scale(ctx, slot_budgets)
            if empty or trimmed or attempt:  # budgets changed → price caps changed
                pools = await self._collect(ctx, slot_budgets, profile)
            finals, unfilled, composer = self._search(ctx, profile, slot_budgets, pools, stay_scale)
            if not unfilled or attempt == passes - 1 or len(slot_budgets) - len(unfilled) < 1:
                break
            # only the earliest hole: later slots are often unfilled *because* of it
            order = [sb.slot.position for sb in slot_budgets]
            hole = min(unfilled, key=order.index)
            if hole not in optional:
                warnings.append(_slot_empty(hole, role_of[hole]))
            slot_budgets = B.drop_slot(slot_budgets, hole, b)
        if ctx.focus_request and ctx.focus != ctx.focus_request:
            warnings.append(_focus_unavailable(ctx))
        if trimmed and ctx.duration_min:
            warnings.insert(0, _duration_fit(ctx.duration_min, len(slot_budgets), trimmed))
        candidates_count = len({(p.is_event, p.id) for pool in pools.values() for p in pool})
        if not finals:
            raise NoCourseError("no feasible course")
        warnings.extend(_slot_empty(pos, role_of[pos]) for pos in unfilled if pos not in optional)

        chosen: list[tuple[str, Partial, CourseComposer]] = [(PRIMARY_LABEL, finals[0], composer)]
        selected: list[Key] = [finals[0].keys]
        if ctx.alternatives > 0:
            for variant in params.variants or DEFAULT_VARIANTS:
                if len(chosen) > ctx.alternatives:
                    break
                vprofile = variant_profile(profile, variant)
                vfinals, _, vcomposer = self._search(ctx, vprofile, slot_budgets, pools, stay_scale)
                pick = self._pick(ctx, vfinals, selected, b, vprofile, strict_only=True)
                if pick is not None:
                    chosen.append((str(variant.get("label", FALLBACK_LABEL)), pick, vcomposer))
                    selected.append(pick.keys)
            while len(chosen) <= ctx.alternatives:
                pick = self._pick(ctx, finals, selected, b, profile, strict_only=False)
                if pick is None:
                    break
                chosen.append((FALLBACK_LABEL, pick, composer))
                selected.append(pick.keys)

        courses = []
        for label, partial, comp in chosen:
            routed, solver = self._route(partial, comp)
            routed = await self._remeasure(routed, ctx, comp)
            courses.append(self._to_course(label, routed, template, ctx, profile, solver, warnings))
        return EngineOutput(
            courses=courses,
            template=template,
            candidates_count=candidates_count,
            warnings=warnings,
            stay_scale=stay_scale,
        )

    # --- candidates --------------------------------------------------------------------------

    @staticmethod
    def _stay_scale(ctx: RequestContext, slot_budgets: Sequence[B.SlotBudget]) -> float:
        """Scale stays to the requested window: shorter for a tight one, longer for a long one.

        A time-gated slot (dinner from 17:00) sets a floor: the stops before it must last until it
        opens, otherwise the course arrives hours early and the slot is dropped as unreachable."""
        slots = len(slot_budgets)
        if not ctx.duration_min or slots == 0:
            return 1.0
        scale = ctx.duration_min / (slots * NOMINAL_SLOT_MIN * ctx.slot_min_scale)
        start_min = ctx.start_at.hour * 60 + ctx.start_at.minute
        for before, sb in enumerate(slot_budgets):
            gate = sb.slot.earliest_start_min
            if before and gate is not None and gate > start_min:
                # real stays run a little under nominal (cafés 50, walks 45) → aim slightly past the gate
                scale = max(scale, GATE_MARGIN * (gate - start_min) / (before * NOMINAL_SLOT_MIN))
                break
        return max(MIN_STAY_SCALE, min(MAX_STAY_SCALE, scale))

    async def _collect(
        self, ctx: RequestContext, slot_budgets: Sequence[B.SlotBudget], profile: ScoringProfile
    ) -> dict[int, list[PlaceCandidate]]:
        params = profile.params
        if ctx.wanted_categories and not ctx.recentered:
            await self._recenter_on_wanted(ctx, slot_budgets)
        await self._settle_on_foot(ctx, slot_budgets)
        if not ctx.core_radius_m:
            ctx.core_radius_m = ctx.radius_m
        cache: dict[tuple[str, float], list[PlaceCandidate]] = {}
        pools: dict[int, list[PlaceCandidate]] = {}
        rings: dict[int, list[PlaceCandidate]] = {}
        for i, sb in enumerate(slot_budgets):
            est_arrive = ctx.start_at + timedelta(minutes=i * NOMINAL_SLOT_MIN + 10)
            fc = FilterContext.build(ctx, sb.slot.course_role, sb.budget, est_arrive)
            # opening hours are filtered on the estimated arrival here and re-checked exactly in the beam
            radius = float(ctx.radius_m)
            pool: list[PlaceCandidate] = []
            back: list[PlaceCandidate] = []  # a regular's past places let back in (see below)
            for _attempt in range(params.radius_expand_max + 1):
                key = (sb.slot.course_role, radius)
                if key not in cache:
                    cache[key] = await self._source.fetch(
                        sb.slot.course_role, ctx.origin, radius, ctx.start_at.date(), ctx.local_words
                    )
                pool = hard_filter(cache[key], fc, params)
                if ctx.been_place_ids and not pool and not back:
                    # 자주: when nothing else is this near, a place they have been to beats a longer walk to
                    # one they have not (2026-09-26: a 32-minute walk to the next pub past the one they
                    # knew). Let back in, it stays in the pool as the search goes further.
                    back = been_places(cache[key], fc, ctx, params)
                pool = [*pool, *back]
                if not pool and ctx.avoid_tags_by_role:
                    # "no chains" is a preference of the style, not the user's veto: a 2,700원 café budget
                    # only buys a chain, and an empty café stop is worse than a Mega Coffee
                    pool = hard_filter(
                        cache[key],
                        replace(
                            fc,
                            disliked_tags=frozenset(ctx.disliked_tags) | never_tags(ctx, sb.slot.course_role),
                        ),
                        params,
                    )
                if len(pool) >= params.min_candidates:
                    break
                radius *= params.radius_expand_factor
            pools[sb.slot.position] = pool
            if ctx.is_v2:
                role = sb.slot.course_role
                rings[sb.slot.position] = await self._ring(ctx, role, fc, radius, params, cache)
        every = [p for group in (*pools.values(), *rings.values()) for p in group]
        assign_buzz([*every, *ctx.kept_places])
        mark_local([*every, *ctx.kept_places], ctx, get_signature_rules())
        if is_regular(ctx):  # a regular is pulled toward what opened lately (the licence date, where known)
            opened = getattr(self._source, "opened_on", None)
            if opened is not None:
                mark_opened(every, await opened([p.id for p in every if not p.is_event]))
        if rings:
            pools = self._admit_rings(ctx, pools, rings, params)
        unfiltered = [p for found in cache.values() for p in found]
        # the pinned stops first: whatever else is asked for by name goes into the other slots
        positions = [(sb.slot.position, sb.slot.course_role) for sb in slot_budgets]
        pools = kept_pools(pools, positions, ctx.kept_places)
        pools = wanted_pools(pools, ctx.wanted_categories)
        pools = wanted_places(pools, ctx.wanted_place_ids)
        pools = wanted_events(pools, ctx.wanted_event_ids)
        return focus_pools(pools, ctx, get_signature_rules(), unfiltered)

    async def _ring(
        self,
        ctx: RequestContext,
        role: str,
        fc: FilterContext,
        core: float,
        params: Any,
        cache: dict[tuple[str, float], list[PlaceCandidate]],
    ) -> list[PlaceCandidate]:
        """v2 adaptive reach (docs/29 §2): the places of the adjacent rings that pass the hard filters.
        Whether any of them is worth the trip is decided once the whole pool is marked (`_admit_rings`)."""
        found: dict[tuple[bool, int], PlaceCandidate] = {}
        tiers = day_score.reach_tiers(params, ctx)
        # the rings are nested: one fetch at the outermost covers them all (the travel curve, not the ring,
        # decides how much further costs)
        for mult in tiers[-1:]:
            radius = min(ctx.core_radius_m * mult, params.reach_max_m(ctx.transport))
            if radius <= core:
                continue
            key = (role, -radius)  # a separate cache line: these are standouts only, not the whole ring
            if key not in cache:
                standouts = getattr(self._source, "fetch_standouts", None)
                cache[key] = (
                    await standouts(
                        role,
                        ctx.origin,
                        radius,
                        min_popularity=params.worth_trip_min,
                        name_words=ctx.local_words,
                        place_ids=sorted(ctx.landmark_ids),
                    )
                    if standouts is not None
                    else await self._source.fetch(
                        role, ctx.origin, radius, ctx.start_at.date(), ctx.local_words
                    )
                )
            for p in hard_filter(cache[key], fc, params):
                if haversine_m(ctx.origin, p.point) > core:
                    found.setdefault((p.is_event, p.id), p)
        return list(found.values())

    @staticmethod
    def _admit_rings(
        ctx: RequestContext,
        pools: dict[int, list[PlaceCandidate]],
        rings: dict[int, list[PlaceCandidate]],
        params: Any,
    ) -> dict[int, list[PlaceCandidate]]:
        """A place beyond the neighbourhood joins only when it is worth going further for: what the area
        is known for, vouched for by a public body, measurably visited, or a strong match for the purpose.
        A far place that is merely as good as a near one never gets in (docs/29 §2 "확장할 가치").
        Joining is not winning: it still has to beat the near places on the day score."""
        listed = get_signature_rules().listed_score
        out = dict(pools)
        for position, ring in rings.items():

            def worth(p: PlaceCandidate) -> float:
                purpose = F.purpose_fit(p.tags, ctx.purpose_tag_affinity)
                vouched = listed if p.is_curated else 0.0
                return max(p.local_score, vouched, p.popularity, purpose if purpose >= 0.7 else 0.0)

            standouts = sorted(
                (p for p in ring if worth(p) >= params.worth_trip_min), key=lambda p: (-worth(p), p.id)
            )[: params.ring_seats]
            if standouts:
                out[position] = [*pools.get(position, []), *standouts]
                ctx.ring_keys |= {(p.is_event, p.id) for p in standouts}
        return out

    async def _recenter_on_wanted(self, ctx: RequestContext, slot_budgets: Sequence[B.SlotBudget]) -> None:
        """The user asked for a kind of place by name (a ballpark) and the neighbourhood's radius does
        not reach one: look `WANTED_REACH_M` out, and if it is there plan the day around it. A course
        whose one fixed point is a 25-minute walk from everything else is not a course."""
        ctx.recentered = True
        for category in ctx.wanted_categories:
            for role in dict.fromkeys(sb.slot.course_role for sb in slot_budgets):
                found = await self._source.fetch(role, ctx.origin, WANTED_REACH_M, ctx.start_at.date())
                matching = [c for c in found if c.category_code == category]
                if not matching:
                    continue
                nearest = min(matching, key=lambda c: haversine_m(ctx.origin, c.point))
                if haversine_m(ctx.origin, nearest.point) > ctx.radius_m * RECENTER_BEYOND:
                    ctx.origin = nearest.point
                return

    async def _settle_on_foot(self, ctx: RequestContext, slot_budgets: Sequence[B.SlotBudget]) -> None:
        """On foot in a district wider than anyone walks: first find where to walk.

        The best restaurants and the best cafés of a 5 km district rarely stand in the same street; the
        beam took the top restaurant (a far-off mall), found nothing within a walk of it and returned a
        one-stop course. A person would pick the liveliest pocket of the district first: the 1.5 km block
        where the most KINDS of places for this course stand together, then the most places."""
        if (
            ctx.transport != "walk"
            or ctx.radius_m <= WALK_AREA_M
            or ctx.recentered
            or ctx.wanted_place_ids
            or ctx.anchored
            or ctx.kept_places  # the pinned stops already say where the day is
        ):
            return
        d_lat = WALK_CELL_M / 111_000
        d_lng = d_lat / max(0.2, math.cos(math.radians(ctx.origin.lat)))
        cells: dict[tuple[int, int], list[tuple[str, GeoPoint]]] = {}
        for role in dict.fromkeys(sb.slot.course_role for sb in slot_budgets):
            found = await self._source.fetch(role, ctx.origin, float(ctx.radius_m), ctx.start_at.date())
            for c in found:
                cells.setdefault((round(c.lat / d_lat), round(c.lng / d_lng)), []).append((role, c.point))
        if not cells:
            return

        def block(cell: tuple[int, int]) -> list[tuple[str, GeoPoint]]:
            return [
                x
                for dy in (-1, 0, 1)
                for dx in (-1, 0, 1)
                for x in cells.get((cell[0] + dy, cell[1] + dx), ())
            ]

        best = max(cells, key=lambda cell: (len({role for role, _ in block(cell)}), len(block(cell))))
        points = [p for _, p in block(best)]
        ctx.origin = GeoPoint(
            sum(p.lat for p in points) / len(points), sum(p.lng for p in points) / len(points)
        )
        ctx.radius_m = WALK_AREA_M
        ctx.recentered = True

    # --- search ------------------------------------------------------------------------------

    def _search(
        self,
        ctx: RequestContext,
        profile: ScoringProfile,
        slot_budgets: Sequence[B.SlotBudget],
        pools: dict[int, list[PlaceCandidate]],
        stay_scale: float,
    ) -> tuple[list[Partial], list[int], CourseComposer]:
        composer = CourseComposer(PlaceScorer(profile, ctx), ctx, self._est, stay_scale)
        ranked = {
            sb.slot.position: composer.rank(
                pools[sb.slot.position], sb, ctx.start_at + timedelta(minutes=i * NOMINAL_SLOT_MIN + 10)
            )
            for i, sb in enumerate(slot_budgets)
        }
        finals, unfilled = composer.search(slot_budgets, ranked)
        return finals, unfilled, composer

    @staticmethod
    def _pick(
        ctx: RequestContext,
        finals: Sequence[Partial],
        selected: Sequence[Key],
        b: float,
        profile: ScoringProfile,
        *,
        strict_only: bool,
    ) -> Partial | None:
        params = profile.params
        pool = list(finals[:MMR_POOL])
        pick = mmr_pick(
            pool,
            selected,
            key=lambda p: p.keys,
            relevance=lambda p: objective(p, b, params, final=True, ctx=ctx),
            lam=params.mmr_lambda,
            max_overlap=params.max_overlap if strict_only else 1.0,
        )
        if pick is None:
            return None
        if strict_only and any(
            len(pick.keys & s) / max(len(pick.keys), len(s)) >= params.max_overlap for s in selected
        ):
            return None
        return pick

    # --- routing -----------------------------------------------------------------------------

    def _route(self, partial: Partial, composer: CourseComposer) -> tuple[Partial, str]:
        stops = partial.stops
        problem = self._route_problem(partial, composer)
        solution = optimize(problem)
        identity = list(range(1, len(stops) + 1))
        if solution.feasible and solution.order != identity:
            sequence = [(stops[i - 1].place, stops[i - 1].sb) for i in solution.order]
            replanned = composer.replan(sequence, strict=True)
            if replanned is not None and self._better_order(replanned, partial, composer):
                return replanned, solution.solver
        return partial, solution.solver

    @staticmethod
    def _better_order(replanned: Partial, partial: Partial, composer: CourseComposer) -> bool:
        """v1: less travel wins. v2: the reordered day must score at least as well as a whole."""
        ctx, params = composer._ctx, composer._params
        if not ctx.is_v2:
            return replanned.travel_min < partial.travel_min
        b = ctx.budget_per_person
        before = objective(partial, b, params, final=True, ctx=ctx)
        after = objective(replanned, b, params, final=True, ctx=ctx)
        return after >= before and replanned.travel_min <= partial.travel_min

    def _route_problem(self, partial: Partial, composer: CourseComposer) -> RouteProblem:
        ctx = composer._ctx
        stops = partial.stops
        points = [ctx.origin, *(s.place.point for s in stops)]
        travel = [
            [self._est.estimate(a, c, ctx.transport).minutes if a != c else 0.0 for c in points]
            for a in points
        ]
        stay = [0.0, *(float((s.leave - s.arrive).total_seconds() // 60) for s in stops)]
        flex = [s.sb.slot.is_order_flexible for s in stops]
        precedence = [
            (i + 1, j + 1)
            for i in range(len(stops))
            for j in range(i + 1, len(stops))
            if not all(flex[i : j + 1])
        ]
        windows: list[list[Window]] = [[]]
        for s in stops:
            windows.append(_arrival_windows(s.place, s.sb.slot, ctx.start_at, int(stay[len(windows)])))
        return RouteProblem(
            travel=travel,
            stay=stay,
            windows=windows,
            precedence=precedence,
            max_wait=float(composer._params.max_wait_min),
        )

    async def _remeasure(self, partial: Partial, ctx: RequestContext, composer: CourseComposer) -> Partial:
        """Only the legs of the final courses hit the real routing API (≤ 12 calls per request)."""
        if self._travel is None or isinstance(self._travel, HaversineEstimator):
            return partial
        measured: dict[tuple[GeoPoint, GeoPoint], Leg] = {}
        prev = ctx.origin
        for s in partial.stops:
            with contextlib.suppress(TravelTimeError):  # keep the haversine estimate for this leg
                measured[(prev, s.place.point)] = await self._travel.leg(prev, s.place.point, ctx.transport)
            prev = s.place.point
        if not measured:
            return partial
        precise = CourseComposer(composer._scorer, ctx, _MeasuredEstimator(measured), composer._stay_scale)
        sequence = [(s.place, s.sb) for s in partial.stops]
        return precise.replan(sequence, strict=False) or partial

    # --- output ------------------------------------------------------------------------------

    @staticmethod
    def _to_course(
        label: str,
        partial: Partial,
        template: Template,
        ctx: RequestContext,
        profile: ScoringProfile,
        solver: str,
        warnings: Sequence[dict[str, Any]],
    ) -> CourseResult:
        return build_course(label, partial, template.id, ctx, profile, solver, warnings)


def build_course(
    label: str,
    partial: Partial,
    template_id: int,
    ctx: RequestContext,
    profile: ScoringProfile,
    solver: str,
    warnings: Sequence[dict[str, Any]] = (),
) -> CourseResult:
    stops = [
        StopResult(
            position=i + 1,
            role=s.place.course_role,
            place=s.place,
            arrive_at=s.arrive,
            leave_at=s.leave,
            est_price=s.place.price * ctx.party_size,
            travel_min_from_prev=round(s.leg.minutes),
            distance_m_from_prev=round(s.leg.distance_m),
            score=s.score.total,
            score_breakdown=s.score.breakdown,
            congestion=s.congestion,
            slot_budget=s.eff_budget,
            slot=s.sb.slot,
            slot_share=s.sb.share,
            slot_base_budget=s.sb.budget,
            reason_codes=day_score.reason_codes(s, partial.stops, ctx, profile.params),
        )
        for i, s in enumerate(partial.stops)
    ]
    total_price = sum(s.est_price for s in stops)
    course_warnings = list(warnings)
    if total_price > ctx.budget_total:
        over = total_price - ctx.budget_total
        course_warnings.append(
            {"code": "BUDGET_OVER", "detail": f"예산을 {over:,}원 초과해요.", "meta": {"over": over}}
        )
    return CourseResult(
        label=label,
        template_id=template_id,
        stops=stops,
        total_price=total_price,
        total_travel_min=sum(s.travel_min_from_prev for s in stops),
        total_distance_m=sum(s.distance_m_from_prev for s in stops),
        duration_min=int((stops[-1].leave_at - ctx.start_at).total_seconds() // 60) if stops else 0,
        score=round(partial.score_sum / max(1, len(stops)), 4),
        objective=round(objective(partial, ctx.budget_per_person, profile.params, final=True, ctx=ctx), 4),
        optimizer=solver,
        warnings=course_warnings,
    )


def _kept_count(out: EngineOutput, ctx: RequestContext) -> int:
    keys = ctx.kept_keys
    return sum(1 for s in out.courses[0].stops if (s.place.is_event, s.place.id) in keys)


def _empty_slots(out: EngineOutput) -> int:
    return sum(1 for w in out.courses[0].warnings if w.get("code") == "SLOT_EMPTY")


def _has_role(out: EngineOutput, roles: frozenset[str]) -> bool:
    return any(s.role in roles for s in out.courses[0].stops)


def _no_worse_filled(other: EngineOutput, out: EngineOutput) -> bool:
    """A different structure only wins as a whole day: as many stops, and no slot it could not fill (the day
    score is a per-stop average, so a shorter day could otherwise look better)."""
    return len(other.courses[0].stops) >= len(out.courses[0].stops) and _empty_slots(other) <= _empty_slots(
        out
    )


def _slot_empty(position: int, role: str) -> dict[str, Any]:
    return {
        "code": "SLOT_EMPTY",
        "detail": "조건에 맞는 장소를 찾지 못해 이 단계는 건너뛰었어요.",
        "meta": {"position": position, "role": role},
    }


def _focus_unavailable(ctx: RequestContext) -> dict[str, Any]:
    """The user picked a local specialty and the course could not carry it: say why, never swap silently."""
    word, price = ctx.focus_request, ctx.focus_from_price
    if price:
        total = price * ctx.party_size
        detail = (
            f"'{word}' 집은 {ctx.party_size}명이면 {total:,}원쯤부터라 이번 예산 배분에는 넣지 못했어요. "
            "예산을 올리거나 들르는 곳을 줄이면 넣을 수 있어요."
        )
    else:
        detail = f"이 시간에 문을 연 '{word}' 집을 찾지 못했어요. 시간을 바꾸면 넣을 수 있어요."
    return {"code": "FOCUS_UNAVAILABLE", "detail": detail, "meta": {"focus": word, "from_price": price}}


def _duration_fit(duration_min: int, kept: int, trimmed: Sequence[Any]) -> dict[str, Any]:
    hours = duration_min / 60
    span = f"{hours:g}시간"
    return {
        "code": "DURATION_FIT",
        "detail": f"{span} 일정에 맞춰 들르는 곳 수와 머무는 시간을 조절했어요.",
        "meta": {
            "duration_min": duration_min,
            "slots": kept,
            "dropped_roles": [s.course_role for s in trimmed],
        },
    }


def _arrival_windows(place: PlaceCandidate, slot: Any, start_at: datetime, stay: int) -> list[Window]:
    """Feasible ARRIVAL intervals in minutes relative to `start_at` (opening hours ∩ slot window)."""
    day0 = start_at.replace(hour=0, minute=0, second=0, microsecond=0)
    offset = (start_at - day0).total_seconds() / 60.0
    buffer = min(stay, MIN_OPEN_BUFFER_MIN)
    opens: list[Window] = []
    if not place.opening_hours:
        opens.append((-math.inf, math.inf))
    for p in place.opening_hours:
        if p.is_closed:
            continue
        shift = {
            start_at.weekday(): 0,
            (start_at.weekday() - 1) % 7: -1440,
            (start_at.weekday() + 1) % 7: 1440,
        }
        if p.dow not in shift:
            continue
        lo, hi = p.open_min + shift[p.dow], p.close_min + shift[p.dow] - buffer
        if p.break_start_min is not None and p.break_end_min is not None:
            opens.append((lo, p.break_start_min + shift[p.dow] - buffer))
            opens.append((p.break_end_min + shift[p.dow], hi))
        else:
            opens.append((lo, hi))
    s_lo = slot.earliest_start_min if slot.earliest_start_min is not None else -math.inf
    s_hi = slot.latest_start_min if slot.latest_start_min is not None else math.inf
    if s_hi < s_lo:
        s_hi += 1440
    out: list[Window] = []
    for o_lo, o_hi in opens:
        lo2, hi2 = max(o_lo, s_lo) - offset, min(o_hi, s_hi) - offset
        if hi2 >= lo2 and hi2 >= 0:
            out.append((lo2, hi2))
    return out or [(math.inf, math.inf)]
