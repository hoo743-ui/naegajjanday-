from __future__ import annotations

import random
from collections.abc import Sequence
from datetime import date

import pytest

from app.domain.models import GeoPoint, NoCourseError, PlaceCandidate, Slot
from app.domain.recommendation import budget as B
from app.domain.recommendation.composer import CourseComposer, objective
from app.domain.recommendation.diversify import DEFAULT_VARIANTS, mmr_pick, overlap, variant_profile
from app.domain.recommendation.engine import RecommendationEngine
from app.domain.recommendation.scorer import PlaceScorer
from app.domain.routing.travel_time import haversine_m
from tests.factories import DATE_EVENING, ORIGIN, all_week, context, place, profile, template

MEAL_CATS = ["food.korean", "food.noodle", "food.japanese", "food.western", "food.asian"]
CAFE_CATS = ["cafe.coffee", "cafe.roastery", "cafe.book", "cafe.view"]


def world(seed: int = 7) -> list[PlaceCandidate]:
    rng = random.Random(seed)

    def near() -> dict[str, float]:
        return {"dlat": rng.uniform(-0.004, 0.004), "dlng": rng.uniform(-0.004, 0.004)}

    hours = all_week(10 * 60, 23 * 60)
    places = [
        place(
            "MEAL",
            rng.choice(MEAL_CATS),
            rng.choice([7000, 9000, 11000, 12000, 13500, 16000]),
            opening_hours=hours,
            **near(),
        )
        for _ in range(14)
    ]
    places += [
        place(
            "CAFE", rng.choice(CAFE_CATS), rng.choice([3500, 4500, 5000, 6000]), opening_hours=hours, **near()
        )
        for _ in range(10)
    ]
    places += [
        place("ATTRACTION", f"attraction.{k}", None, **near())
        for k in ("park", "street", "market", "landmark")
    ]
    places += [
        place("BAR", "bar.pub", 18000, opening_hours=all_week(17 * 60, 26 * 60), **near()) for _ in range(3)
    ]
    return places


class FakeSource:
    def __init__(self, places: list[PlaceCandidate]) -> None:
        self.places = places
        self.calls: list[tuple[str, float]] = []

    async def fetch(
        self, role: str, origin: GeoPoint, radius_m: float, on_date: date, name_words: Sequence[str] = ()
    ) -> list[PlaceCandidate]:
        self.calls.append((role, radius_m))
        return [p for p in self.places if p.course_role == role and haversine_m(origin, p.point) <= radius_m]


def beam(budget_total: int = 40000) -> tuple[list, CourseComposer, float]:
    ctx, prof = context(budget_total=budget_total), profile()
    composer = CourseComposer(PlaceScorer(prof, ctx), ctx)
    slot_budgets = B.allocate(DATE_EVENING, ctx.budget_per_person)
    ranked = {
        sb.slot.position: composer.rank(
            [p for p in world() if p.course_role == sb.slot.course_role], sb, ctx.start_at
        )
        for sb in slot_budgets
    }
    finals, unfilled = composer.search(slot_budgets, ranked)
    assert not unfilled
    return finals, composer, ctx.budget_per_person


class TestBeamSearch:
    def test_every_course_respects_budget_tolerance(self) -> None:
        finals, _, b = beam()
        assert finals and len(finals) <= 40
        assert all(p.spent <= b for p in finals)

    def test_no_duplicate_place_or_sub_category(self) -> None:
        finals, _, _ = beam()
        for p in finals:
            cats = [s.place.category_code for s in p.stops]
            assert len(set(cats)) == len(cats)
            assert len(p.keys) == len(p.stops)

    def test_sorted_by_objective_and_roles_in_template_order(self) -> None:
        finals, composer, b = beam()
        values = [objective(p, b, composer._params, final=True) for p in finals]
        assert values == sorted(values, reverse=True)
        assert [s.place.course_role for s in finals[0].stops] == ["MEAL", "CAFE", "ATTRACTION"]

    def test_top_k_limits_candidates_per_slot(self) -> None:
        ctx, prof = context(), profile(top_k=3)
        composer = CourseComposer(PlaceScorer(prof, ctx), ctx)
        sb = B.allocate(DATE_EVENING, ctx.budget_per_person)[0]
        assert len(composer.rank([p for p in world() if p.course_role == "MEAL"], sb, ctx.start_at)) == 3

    def test_shortlist_is_not_owned_by_one_category(self) -> None:
        """양식만 20곳이 상위를 채워도, 점심+저녁처럼 같은 역할이 두 번 나오는 코스가 저녁을 고를 수 있어야 한다."""
        ctx, prof = context(), profile()
        composer = CourseComposer(PlaceScorer(prof, ctx), ctx)
        sb = B.allocate(DATE_EVENING, ctx.budget_per_person)[0]
        western = [place("MEAL", "food.western", 11000, rating_avg=4.9) for _ in range(20)]
        others = [place("MEAL", c, 11000, rating_avg=3.6) for c in ("food.korean", "food.japanese")]
        ranked = composer.rank(western + others, sb, ctx.start_at)
        assert {p.category_code for p in ranked} == {"food.western", "food.korean", "food.japanese"}
        assert sum(p.category_code == "food.western" for p in ranked) <= 3

    def test_carry_over_rescoring_uses_saved_money(self) -> None:
        ctx, prof = context(), profile()
        composer = CourseComposer(PlaceScorer(prof, ctx), ctx)
        meal_sb, cafe_sb = B.allocate(DATE_EVENING, ctx.budget_per_person)[:2]
        cafe = place("CAFE", "cafe.view", 6500)
        thrifty = composer.extend(composer.empty(), place("MEAL", "food.noodle", 7000), meal_sb)
        spender = composer.extend(composer.empty(), place("MEAL", "food.bbq", 13500), meal_sb)
        assert thrifty and spender
        rich, poor = composer.extend(thrifty, cafe, cafe_sb), composer.extend(spender, cafe, cafe_sb)
        assert rich and poor
        assert rich.stops[-1].eff_budget == pytest.approx(5000 + 6750)
        assert rich.stops[-1].score.breakdown["budget"] > poor.stops[-1].score.breakdown["budget"]

    def test_leg_longer_than_walk_limit_is_rejected(self) -> None:
        ctx, prof = context(), profile()
        composer = CourseComposer(PlaceScorer(prof, ctx), ctx)
        meal_sb, cafe_sb = B.allocate(DATE_EVENING, ctx.budget_per_person)[:2]
        first = composer.extend(composer.empty(), place("MEAL", "food.korean", 11000), meal_sb)
        assert first is not None
        far_cafe = place("CAFE", "cafe.coffee", 4500, dlat=0.02)  # ≈ 2.2 km → ≈ 38 min on foot
        assert composer.extend(first, far_cafe, cafe_sb) is None

    def test_slot_window_blocks_early_bar(self) -> None:
        ctx, prof = context(budget_total=200000, start_at=context().start_at.replace(hour=14)), profile()
        composer = CourseComposer(PlaceScorer(prof, ctx), ctx)
        bar_sb = B.allocate(DATE_EVENING, ctx.budget_per_person)[3]
        bar = place("BAR", "bar.pub", 18000, opening_hours=all_week(12 * 60, 26 * 60))
        assert composer.extend(composer.empty(), bar, bar_sb) is None  # 14:00 is > 45 min before 17:00


class TestDiversify:
    def test_overlap(self) -> None:
        a = frozenset({(False, 1), (False, 2), (False, 3)})
        assert overlap(a, frozenset({(False, 1), (False, 8), (False, 9)})) == pytest.approx(1 / 3)
        assert overlap(a, a) == 1.0

    def test_mmr_skips_near_duplicates(self) -> None:
        a = frozenset({(False, 1), (False, 2), (False, 3)})
        near_dup = frozenset({(False, 1), (False, 2), (False, 9)})
        fresh = frozenset({(False, 7), (False, 8), (False, 3)})
        pool = [(near_dup, 0.9), (fresh, 0.7)]
        pick = mmr_pick(pool, [a], key=lambda t: t[0], relevance=lambda t: t[1], lam=0.7, max_overlap=0.5)
        assert pick == (fresh, 0.7)

    def test_variant_profiles_twist_weights(self) -> None:
        base = profile()
        cheap = variant_profile(base, DEFAULT_VARIANTS[0])
        assert cheap.normalized_weights()["budget"] > base.normalized_weights()["budget"]
        assert cheap.params.budget_target_util == 0.6
        assert sum(cheap.normalized_weights().values()) == pytest.approx(1.0)


class TestEngine:
    async def test_generates_primary_and_distinct_alternatives(self) -> None:
        engine = RecommendationEngine(FakeSource(world()))
        out = await engine.generate(context(alternatives=2), [DATE_EVENING], profile())
        assert out.courses[0].label == "추천 코스"
        assert len(out.courses) == 3
        keys = [c.place_ids for c in out.courses]
        assert len(set(keys)) == 3
        for c in out.courses:
            assert c.total_price == sum(s.est_price for s in c.stops)
            assert c.total_price <= 40000
            assert [s.position for s in c.stops] == list(range(1, len(c.stops) + 1))
            assert c.optimizer == "held_karp"

    async def test_empty_slot_is_skipped_with_warning_and_radius_expanded(self) -> None:
        places = [p for p in world() if p.course_role != "ATTRACTION"]
        source = FakeSource(places)
        out = await RecommendationEngine(source).generate(context(alternatives=0), [DATE_EVENING], profile())
        assert [w["code"] for w in out.warnings] == ["SLOT_EMPTY"]
        assert [s.role for s in out.courses[0].stops] == ["MEAL", "CAFE"]
        radii = sorted({r for role, r in source.calls if role == "ATTRACTION"})
        assert radii == [1200.0, 1800.0, 2700.0]  # x1.5, at most twice

    async def test_no_places_raises(self) -> None:
        with pytest.raises(NoCourseError):
            await RecommendationEngine(FakeSource([])).generate(context(), [DATE_EVENING], profile())

    async def test_flexible_slots_are_reordered_to_shorten_the_walk(self) -> None:
        t = template(
            Slot(1, "ATTRACTION", 0.0, is_order_flexible=True),
            Slot(2, "CULTURE", 0.0, is_order_flexible=True),
            Slot(3, "MEAL", 1.0),
            min_budget=5000,
        )
        far = place("ATTRACTION", "attraction.park", None, dlat=0.006)
        near = place("CULTURE", "culture.gallery", None, dlat=0.001)
        meal = place("MEAL", "food.korean", 17000, dlat=0.0065, opening_hours=all_week(10 * 60, 23 * 60))
        out = await RecommendationEngine(FakeSource([far, near, meal])).generate(
            context(alternatives=0), [t], profile(min_candidates=1)
        )
        course = out.courses[0]
        assert [s.place.id for s in course.stops] == [
            near.id,
            far.id,
            meal.id,
        ]  # MEAL stays last (precedence)
        assert ORIGIN is not None
