"""Algorithm v2 (docs/29): distance is a preference, the whole day is scored, and further only when worth it."""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.domain.models import ScoringProfile, Slot
from app.domain.recommendation import budget as B
from app.domain.recommendation import day_score as D
from app.domain.recommendation.composer import CourseComposer
from app.domain.recommendation.engine import RecommendationEngine
from app.domain.recommendation.scorer import PlaceScorer
from tests.factories import DATE_EVENING, DEFAULT_WEIGHTS, all_week, context, place, profile, template
from tests.unit.test_composer_engine import FakeSource, world

CURVE = [[0.0, 0.0], [1.0, 0.015], [2.0, 0.06], [3.0, 0.16], [4.0, 0.36]]
HOURS = all_week(10 * 60, 24 * 60)


class TestTravelCurve:
    def test_small_differences_cost_little_and_long_legs_a_lot(self) -> None:
        def pen(minutes: float) -> float:
            return D.leg_penalty(minutes, 15, CURVE)

        assert pen(0) == 0
        assert pen(25) - pen(20) < 0.03
        assert pen(60) - pen(45) > 3 * (pen(25) - pen(20))
        assert pen(90) > pen(60)  # past the last knot the last slope continues

    def test_move_style_and_a_short_day_change_the_comfortable_leg(self) -> None:
        params = profile().params
        local, balanced, explorer = (
            D.comfort_min(params, context(move_style=s)) for s in ("local", "balanced", "explorer")
        )
        assert local < balanced < explorer
        assert D.comfort_min(params, context(duration_min=120)) < balanced

    def test_reach_grows_with_the_move_style_and_shrinks_on_a_short_day(self) -> None:
        params = profile().params
        assert D.reach_tiers(params, context(move_style="local")) == []
        assert len(D.reach_tiers(params, context())) == 2
        assert len(D.reach_tiers(params, context(move_style="explorer"))) == 3
        assert len(D.reach_tiers(params, context(duration_min=150))) == 1


class TestSoftLegs:
    def _two_stops(self, algorithm: str, far_dlat: float) -> bool:
        ctx = context(algorithm=algorithm)
        composer = CourseComposer(PlaceScorer(profile(), ctx), ctx)
        slots = B.allocate(DATE_EVENING, ctx.budget_per_person)
        meal = place("MEAL", "food.korean", 12000, opening_hours=HOURS)
        cafe = place("CAFE", "cafe.coffee", 5000, opening_hours=HOURS, dlat=far_dlat)
        first = composer.extend(composer.empty(), meal, slots[0])
        assert first is not None
        return composer.extend(first, cafe, slots[1]) is not None

    def test_v1_forbids_a_25_minute_walk_and_v2_prices_it(self) -> None:
        assert not self._two_stops("v1", 0.013)  # ~1.4 km straight, ~25 min on foot
        assert self._two_stops("v2", 0.013)

    def test_v2_still_forbids_what_nobody_would_walk(self) -> None:
        assert not self._two_stops("v2", 0.03)  # ~3.3 km straight, ~55 min on foot


def _profile_with_curated() -> ScoringProfile:
    return ScoringProfile("date", 1, {**DEFAULT_WEIGHTS, "curated": 0.15}, profile().params)


def _world_with(extra: list) -> list:
    places = [p for p in world() if p.course_role != "ATTRACTION"]
    # enough ordinary sights nearby that the pool never has to widen on its own
    places += [
        place("ATTRACTION", cat, None, dlat=0.001 * (i + 1))
        for i, cat in enumerate(["attraction.street", "attraction.park", "attraction.market"] * 2)
    ]
    return places + extra


class TestAdaptiveReach:
    async def test_a_standout_beyond_the_area_joins_and_can_win(self) -> None:
        landmark = place(
            "ATTRACTION", "attraction.landmark", None, dlat=0.0125, popularity=1.0, is_curated=True
        )
        engine = RecommendationEngine(FakeSource(_world_with([landmark])))
        ctx = context(algorithm="v2", alternatives=0)
        out = await engine.generate(ctx, [DATE_EVENING], _profile_with_curated())
        chosen = out.courses[0].stops
        hit = next((s for s in chosen if s.place.id == landmark.id), None)
        assert hit is not None
        assert "WORTH_THE_TRIP" in hit.reason_codes

    async def test_v1_never_sees_it(self) -> None:
        landmark = place(
            "ATTRACTION", "attraction.landmark", None, dlat=0.0125, popularity=1.0, is_curated=True
        )
        engine = RecommendationEngine(FakeSource(_world_with([landmark])))
        out = await engine.generate(context(alternatives=0), [DATE_EVENING], _profile_with_curated())
        assert all(s.place.id != landmark.id for s in out.courses[0].stops)

    async def test_a_far_place_that_is_merely_as_good_stays_out(self) -> None:
        plain = place("ATTRACTION", "attraction.street", None, dlat=0.0125)
        engine = RecommendationEngine(FakeSource(_world_with([plain])))
        ctx = context(algorithm="v2", alternatives=0)
        out = await engine.generate(ctx, [DATE_EVENING], _profile_with_curated())
        assert all(s.place.id != plain.id for s in out.courses[0].stops)
        assert (False, plain.id) not in ctx.ring_keys

    async def test_a_local_mover_does_not_look_further(self) -> None:
        landmark = place(
            "ATTRACTION", "attraction.landmark", None, dlat=0.0125, popularity=1.0, is_curated=True
        )
        engine = RecommendationEngine(FakeSource(_world_with([landmark])))
        ctx = context(algorithm="v2", move_style="local", alternatives=0)
        out = await engine.generate(ctx, [DATE_EVENING], _profile_with_curated())
        assert all(s.place.id != landmark.id for s in out.courses[0].stops)


class TestDayScore:
    def _partial(self, roles_and_cats: list[tuple[str, str]], ctx=None):  # type: ignore[no-untyped-def]
        ctx = ctx or context(algorithm="v2")
        composer = CourseComposer(PlaceScorer(profile(), ctx), ctx)
        slots = [
            B.SlotBudget(Slot(i + 1, role, 0.25), 0.25, ctx.budget_per_person / 4)
            for i, (role, _) in enumerate(roles_and_cats)
        ]
        stops = [
            place(role, cat, 5000, opening_hours=HOURS, dlat=0.0005 * i)
            for i, (role, cat) in enumerate(roles_and_cats)
        ]
        partial = composer.replan(list(zip(stops, slots, strict=True)), strict=False)
        assert partial is not None
        return partial, ctx

    def test_four_cafés_lose_to_a_day_with_something_to_do(self) -> None:
        cafes, ctx = self._partial(
            [("CAFE", "cafe.coffee"), ("CAFE", "cafe.book"), ("DESSERT", "dessert"), ("CAFE", "cafe.view")]
        )
        mixed, _ = self._partial(
            [
                ("MEAL", "food.korean"),
                ("CAFE", "cafe.coffee"),
                ("ACTIVITY", "activity.craft"),
                ("NIGHTVIEW", "nightview"),
            ]
        )
        params = profile().params
        a, b = D.breakdown(cafes, ctx, params, final=True), D.breakdown(mixed, ctx, params, final=True)
        assert a["repetition"] < 0 == b["repetition"]
        assert b["experience_diversity"] > a["experience_diversity"]

    def test_a_liked_kind_may_repeat(self) -> None:
        ctx = context(algorithm="v2", category_weights={"cafe": 1.0})
        two, _ = self._partial([("CAFE", "cafe.coffee"), ("CAFE", "cafe.book")], ctx)
        assert D.breakdown(two, ctx, profile().params)["repetition"] == 0

    def test_estimated_prices_near_the_limit_carry_a_budget_risk(self) -> None:
        ctx = context(algorithm="v2", budget_total=10000, party_size=1)
        partial, _ = self._partial([("CAFE", "cafe.coffee"), ("MEAL", "food.korean")], ctx)
        estimated = replace(
            partial,
            stops=tuple(replace(s, place=replace(s.place, price_is_estimated=True)) for s in partial.stops),
        )
        params = profile().params
        assert (
            D.breakdown(estimated, ctx, params)["budget_risk"]
            < D.breakdown(partial, ctx, params)["budget_risk"] + 1e-9
        )
        assert D.breakdown(estimated, ctx, params)["budget_risk"] < 0

    def test_reason_codes_are_known_and_few(self) -> None:
        partial, ctx = self._partial([("MEAL", "food.korean"), ("ACTIVITY", "activity.craft")])
        for s in partial.stops:
            codes = D.reason_codes(s, partial.stops, ctx, profile().params)
            assert set(codes) <= set(D.REASONS)
            assert len(codes) <= D.MAX_REASONS
        second = D.reason_codes(partial.stops[1], partial.stops, ctx, profile().params)
        assert "UNIQUE_EXPERIENCE" in second


class TestStructure:
    def test_a_café_then_a_dessert_café_is_offered_as_café_then_culture(self) -> None:
        t = template(Slot(1, "CAFE", 0.3), Slot(2, "ATTRACTION", 0.05), Slot(3, "DESSERT", 0.25))
        alt = D.structure_alternative(t)
        assert alt is not None
        assert [s.course_role for s in alt.slots] == ["CAFE", "ATTRACTION", "CULTURE"]
        assert alt.slots[2].budget_share == 0.25

    def test_lunch_and_dinner_are_not_a_repetition(self) -> None:
        t = template(Slot(1, "MEAL", 0.4), Slot(2, "CAFE", 0.2), Slot(3, "MEAL", 0.4))
        assert D.structure_alternative(t) is None

    @pytest.mark.parametrize("algorithm", ["v1", "v2"])
    async def test_both_versions_keep_the_budget(self, algorithm: str) -> None:
        engine = RecommendationEngine(FakeSource(world()))
        out = await engine.generate(context(algorithm=algorithm), [DATE_EVENING], profile())
        for course in out.courses:
            assert course.total_price <= 40000
