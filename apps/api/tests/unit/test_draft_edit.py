"""The course as a draft: pinned stops in the engine, and the wishes that nudge a whole day."""

from __future__ import annotations

from datetime import timedelta

from app.domain.models import Slot
from app.domain.recommendation.engine import RecommendationEngine
from app.domain.recommendation.preference import interpret
from app.domain.recommendation.scorer import PlaceScorer, ScoreInput, trait_pull
from app.domain.recommendation.style import kept_pools, with_kept
from app.services.course_service import candidate_line, short_reason
from tests.factories import DATE_EVENING, SUNDAY_6PM, all_week, context, place, profile, template
from tests.unit.test_composer_engine import FakeSource, world


class TestKeptInTheEngine:
    def test_each_pin_takes_the_first_free_slot_of_its_role_and_nowhere_else(self) -> None:
        cafe_a, cafe_b = place("CAFE", "cafe.coffee", 4000), place("CAFE", "cafe.coffee", 5000)
        other = place("CAFE", "cafe.book", 4500)
        pools = {1: [place("MEAL")], 2: [other, cafe_a], 3: [cafe_b, other]}
        out = kept_pools(pools, [(1, "MEAL"), (2, "CAFE"), (3, "CAFE")], [cafe_b, cafe_a])
        assert out[2] == [cafe_b] and out[3] == [cafe_a]  # in the order given
        assert out[1] == pools[1]
        lone = kept_pools({1: [other]}, [(1, "MEAL")], [cafe_a])
        assert lone == {1: [other]}  # no slot of its role: not placed (the service warns)

    def test_templates_get_a_slot_for_every_pin(self) -> None:
        bar = place("BAR", "bar.pub", 18000)
        cafes = [place("CAFE", "cafe.book", 5000), place("CAFE", "cafe.coffee", 4000)]
        two = with_kept([DATE_EVENING], [bar, *cafes], 20000)[0]
        roles = [s.course_role for s in two.slots]
        assert roles.count("CAFE") == 2 and roles.count("BAR") == 1  # one more café slot, the bar slot kept
        assert not next(s for s in two.slots if s.course_role == "BAR").is_optional  # "if it fits" no more
        assert (
            abs(sum(s.budget_share for s in two.slots) - sum(s.budget_share for s in DATE_EVENING.slots))
            < 1e-6
        )

    async def test_a_pinned_place_is_in_the_course_from_outside_the_pool(self) -> None:
        places = world()
        far = place(
            "CAFE", "cafe.coffee", 4500, dlat=0.02, opening_hours=all_week(9 * 60, 23 * 60)
        )  # ~2.2 km
        ctx = context(alternatives=2, kept_places=(far,))
        out = await RecommendationEngine(FakeSource(places)).generate(ctx, [DATE_EVENING], profile())
        assert all((False, far.id) in c.place_ids for c in out.courses)

    async def test_two_pins_of_one_kind_are_both_kept(self) -> None:
        hours = all_week(9 * 60, 23 * 60)
        a = place("CAFE", "cafe.coffee", 4000, dlat=0.001, opening_hours=hours)
        b = place("CAFE", "cafe.coffee", 4500, dlat=-0.001, opening_hours=hours)
        t = template(Slot(1, "MEAL", 0.6), Slot(2, "CAFE", 0.4), min_budget=5000)
        kept = [a, b]
        templates = with_kept([t], kept, 20000)
        ctx = context(alternatives=0, kept_places=tuple(kept))
        out = await RecommendationEngine(FakeSource(world())).generate(ctx, templates, profile())
        ids = out.courses[0].place_ids
        assert (False, a.id) in ids and (False, b.id) in ids

    async def test_a_pin_closed_at_that_hour_is_left_out(self) -> None:
        shut = place("CAFE", "cafe.coffee", 4000, opening_hours=all_week(8 * 60, 12 * 60))
        ctx = context(alternatives=0, kept_places=(shut,))
        out = await RecommendationEngine(FakeSource(world())).generate(ctx, [DATE_EVENING], profile())
        assert (False, shut.id) not in out.courses[0].place_ids and out.courses[0].stops


class TestWishes:
    def test_new_wishes_become_knobs(self) -> None:
        got = interpret(wishes=["quiet", "indoor", "photo", "free"])
        assert got.affinity_add["조용한"] > 0 and got.affinity_add["활기찬"] < 0
        assert got.avoid_roles == {"BAR"} and "activity.karaoke" in got.blocked_categories
        assert got.conditions == ("rain",)  # "실내 위주" is the rainy-day plan
        assert got.trait_pull["photo"] > 0 and got.trait_pull["free"] > 0 and got.trait_pull["buzz"] < 0
        assert got.params["budget_target_util"] <= 0.6 and "ATTRACTION" in got.structure_fill
        assert got.weight_mult["congestion"] > 1.0
        assert "아껴서" in interpret(wishes=["free"], budget_total=40000).summary[-1]["text"]

    def test_the_pull_moves_the_score_and_not_the_breakdown(self) -> None:
        with_photo = place("CAFE", "cafe.coffee", 4000, thumbnail_url="https://tong.visitkorea.or.kr/a.jpg")
        plain = place("CAFE", "cafe.coffee", 4000)
        free = place("ATTRACTION", "attraction.park", None)
        assert trait_pull(with_photo, {"photo": 0.1}) == 0.1 and trait_pull(plain, {"photo": 0.1}) == 0.0
        assert trait_pull(free, {"free": 0.12}) == 0.12 and trait_pull(plain, {"free": 0.12}) == 0.0
        plain.buzz = 1.0
        assert trait_pull(plain, {"buzz": -0.08}) == -0.08

        def score(p: object, pull: dict[str, float]) -> tuple[float, dict[str, float]]:
            ctx = context(trait_pull=pull)
            x = ScoreInput(p, 5000, 0.2, 100.0, SUNDAY_6PM + timedelta(minutes=70), 60)  # type: ignore[arg-type]
            s = PlaceScorer(profile(), ctx).score(x)
            return s.total, s.breakdown

        base, parts = score(with_photo, {})
        pulled, pulled_parts = score(with_photo, {"photo": 0.1})
        assert round(pulled - base, 4) == 0.1 and parts == pulled_parts

    async def test_photo_wish_prefers_the_place_with_a_photo(self) -> None:
        hours = all_week(9 * 60, 23 * 60)
        places = [p for p in world() if p.course_role != "CAFE"]
        # the same café twice over, one with its own photo
        bare = place("CAFE", "cafe.coffee", 4500, dlat=0.0005, opening_hours=hours)
        shot = place("CAFE", "cafe.roastery", 4500, dlat=0.0005, opening_hours=hours, thumbnail_url="x.jpg")
        bare.id, shot.id = 10_001, 10_002  # the plain one wins the id tie-break without the wish

        def cafe(out: object) -> int:
            return next(s.place.id for s in out.courses[0].stops if s.role == "CAFE")  # type: ignore[attr-defined]

        plain = await RecommendationEngine(FakeSource([*places, bare, shot])).generate(
            context(alternatives=0), [DATE_EVENING], profile()
        )
        pulled = await RecommendationEngine(FakeSource([*places, bare, shot])).generate(
            context(alternatives=0, trait_pull={"photo": 0.1}), [DATE_EVENING], profile()
        )
        assert cafe(pulled) == shot.id
        assert cafe(plain) in (bare.id, shot.id)


class TestLines:
    def test_candidate_line_says_what_changes_in_forty_characters(self) -> None:
        p = place("CAFE", "cafe.coffee", 4000)
        assert candidate_line(p, -4000, -3) == "4,000원 아끼고 3분 덜 걸어요"
        assert candidate_line(p, -2000, 2) == "지금보다 2,000원 아껴요"
        assert candidate_line(p, 1000, -5) == "이동이 5분 줄어요"
        assert candidate_line(p, 3000, None) == "3,000원 더 들지만 예산 안이에요"
        assert (
            candidate_line(place("ATTRACTION", "attraction.park", None), 0, 0)
            == "돈 들이지 않고 들를 수 있어요"
        )
        assert all(len(candidate_line(p, d, w)) <= 40 for d in (-(10**9), 0, 10**9) for w in (None, -99, 99))

    def test_short_reason_comes_from_the_codes_only(self) -> None:
        p = place("MEAL", "food.korean", 12000)
        assert short_reason(["PURPOSE_MATCH", "BUDGET_FIT"], p) == "오늘 목적에 잘 맞는 곳"
        assert short_reason(["HIGH_PLACE_QUALITY", "ROUTE_BALANCE"], p) == "앞 장소에서 가까워요"  # no claim
        p.local_word = "꽃게"
        assert short_reason(["LOCAL_SIGNIFICANCE"], p) == "이 동네 명물 꽃게"
        assert short_reason([], p) is None
        assert short_reason([], place("ATTRACTION", "attraction.park", None)) == "돈 들이지 않고 들르는 곳"
