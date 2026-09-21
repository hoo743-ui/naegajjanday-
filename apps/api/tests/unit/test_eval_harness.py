from __future__ import annotations

from datetime import timedelta

from app.domain.models import CourseResult, StopResult
from app.evaluation import harness as H
from tests.factories import SUNDAY_6PM, context, place

SPEC = H.load_spec()
RULES = SPEC["rules"]


def _stop(
    position: int, role: str, category: str, name: str, hour: int, price: int = 10000, walk: int = 5
) -> StopResult:
    arrive = SUNDAY_6PM.replace(hour=hour)
    return StopResult(
        position=position, role=role, place=place(role, category, price, name=name), arrive_at=arrive,
        leave_at=arrive + timedelta(minutes=50), est_price=price * 2, travel_min_from_prev=walk,
        distance_m_from_prev=300, score=0.7, score_breakdown={}, congestion=None, slot_budget=float(price),
    )  # fmt: skip


def _course(stops: list[StopResult]) -> CourseResult:
    return CourseResult(
        label="추천 코스", template_id=1, stops=stops, total_price=sum(s.est_price for s in stops),
        total_travel_min=10, total_distance_m=600, duration_min=180, score=0.7, objective=0.7, optimizer="none",
    )  # fmt: skip


def _codes(stops: list[StopResult], purpose: str = "date", budget: int = 60000) -> set[str]:
    sc = H.Scenario("seoul-hongdae", purpose, "18:30", "efficient", 2, budget)
    return {f.code for f in H.judge(_course(stops), context(), sc, RULES, frozenset({"홍대입구", "홍대"}))}


def test_a_sound_course_has_no_findings() -> None:
    good = [
        _stop(1, "MEAL", "food.western", "파스타집", 18),
        _stop(2, "CAFE", "cafe.coffee", "동네카페", 19, 5000),
        _stop(3, "ATTRACTION", "attraction.street", "경의선책거리", 20, 0),
    ]
    assert _codes(good) == set()


def test_each_clumsy_pattern_is_named() -> None:
    assert "CLOSED_AT_ARRIVAL" in _codes([_stop(1, "CULTURE", "culture.museum", "어느박물관", 20, 0)])
    assert "TOO_EARLY" in _codes([_stop(1, "BAR", "bar.pub", "낮술집", 14)])
    assert "LONG_WALK" in _codes(
        [_stop(1, "MEAL", "food.korean", "밥집", 18), _stop(2, "CAFE", "cafe", "먼카페", 19, 5000, walk=25)]
    )
    assert "SNACK_AS_MEAL" in _codes([_stop(1, "MEAL", "food.snack", "라면분식", 18)])
    assert "VAGUE_SIGHT" in _codes([_stop(1, "ATTRACTION", "attraction.landmark", "홍대", 15, 0)])
    assert "NOT_A_SIGN" in _codes([_stop(1, "MEAL", "food.korean", "하이푸드", 18)])
    assert "FAMILY_BAR" in _codes([_stop(1, "BAR", "bar.pub", "호프", 19)], purpose="family")
    assert "OVER_BUDGET" in _codes([_stop(1, "MEAL", "food.korean", "비싼집", 18, 40000)])


def test_matrix_size_and_filters() -> None:
    assert len(H.build_scenarios(SPEC, "quick", {})) == 4 * 5 * 3 * 2
    only = H.build_scenarios(
        SPEC, "quick", {"region": ["seoul-hongdae"], "purpose": ["date"], "style": ["fun"]}
    )
    assert {(s.region, s.purpose, s.style) for s in only} == {("seoul-hongdae", "date", "fun")} and len(
        only
    ) == 3
    assert only[0].budget_total == 60000 and only[0].party_size == 2
