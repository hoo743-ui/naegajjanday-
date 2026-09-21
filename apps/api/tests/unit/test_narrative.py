from __future__ import annotations

from datetime import datetime, timedelta

from app.domain.models import CourseResult, PlaceCandidate, StopResult
from app.infra.llm.fallback import NullProvider
from app.prompts.loader import PromptLoader, get_prompt_loader
from app.services.narrative_service import NarrativeService
from tests.factories import place

START = datetime(2026, 9, 22, 12, 0)
# words that explain the algorithm instead of talking to the user — the v1 copy was made of these
ALGORITHM_SPEAK = ("동선", "코스에 넣기", "시간대가 잘 맞", "태그가 돋보", "평점", "리뷰")
# hedging that made prices sound unreliable ("38,000원쯤") — say the number and name its source instead
HEDGES = ("원쯤", "원 정도", "원가량", "대략")


def _stop(position: int, cand: PlaceCandidate, est_price: int, travel_min: int = 5) -> StopResult:
    arrive = START + timedelta(hours=position - 1)
    return StopResult(
        position=position,
        role=cand.course_role,
        place=cand,
        arrive_at=arrive,
        leave_at=arrive + timedelta(minutes=50),
        est_price=est_price,
        travel_min_from_prev=travel_min,
        distance_m_from_prev=travel_min * 70,
        score=0.6,
        score_breakdown={"time_fit": 0.9, "distance": 0.8, "budget": 0.7},
        congestion=None,
        slot_budget=20000.0,
    )


def _course(stops: list[StopResult]) -> CourseResult:
    return CourseResult(
        label="추천 코스",
        template_id=1,
        stops=stops,
        total_price=sum(s.est_price for s in stops),
        total_travel_min=sum(s.travel_min_from_prev for s in stops[1:]),
        total_distance_m=1200,
        duration_min=240,
        score=0.6,
        objective=0.6,
        optimizer="held_karp",
    )


def _service(loader: PromptLoader | None = None) -> NarrativeService:
    return NarrativeService(loader or get_prompt_loader(), NullProvider())


def _four_stops() -> CourseResult:
    return _course(
        [
            _stop(1, place("MEAL", "food.bbq", 19000, name="김장독", price_is_estimated=True), 38000),
            _stop(2, place("CAFE", "cafe", 6000, name="홍콩다방", price_is_estimated=True), 12000, 1),
            _stop(3, place("ATTRACTION", "attraction.park", None, name="와우공원"), 0, 11),
            _stop(
                4,
                place("ACTIVITY", "activity.karaoke", 8000, name="코인노래방", price_is_estimated=True),
                16000,
            ),
        ]
    )


def test_lines_talk_about_the_place_price_and_walk_not_about_the_algorithm() -> None:
    n = _service().template(_four_stops(), party_size=2, budget_total=80000, transport="walk")

    assert n.summary == "둘이서 66,000원, 걸어서 17분이면 충분해요"
    for position, name in {1: "김장독", 2: "홍콩다방", 3: "와우공원", 4: "코인노래방"}.items():
        assert name in n.reasons[position]
    for line in n.reasons.values():
        assert not any(word in line for word in ALGORITHM_SPEAK), line
        assert not any(word in line for word in HEDGES), line
        assert "{{" not in line and "  " not in line

    assert n.reasons[1].startswith(("먼저", "시작은")) and "고기" in n.reasons[1]
    assert n.reasons[2].startswith("바로 옆")  # 1 minute away
    assert "11분" in n.reasons[3]
    assert n.reasons[4].startswith(("마지막은", "끝으로"))


def test_price_wording_is_honest_about_estimates() -> None:
    course = _course(
        [
            _stop(1, place("MEAL", "food.korean", 7500, name="삼삼뚝배기", price_is_estimated=False), 15000),
            _stop(2, place("CAFE", "cafe", 6000, name="동네카페", price_is_estimated=True), 12000),
            _stop(3, place("ATTRACTION", "attraction.park", None, name="숲길"), 0),
        ]
    )
    n = _service().template(course, party_size=2, budget_total=50000, transport="walk")

    assert "15,000원 (메뉴판 가격)" in n.reasons[1]  # measured (착한가격업소 menu price)
    assert "12,000원 (업종 평균가)" in n.reasons[2]  # category prior → said as an estimate
    assert "무료" in n.reasons[3] and "평균가" not in n.reasons[3]


def test_no_two_stops_read_the_same() -> None:
    cafes = [
        _stop(i, place("CAFE", "cafe", 6000, name=f"카페{i}", price_is_estimated=True), 12000, 4)
        for i in range(1, 5)
    ]
    n = _service().template(_course(cafes), party_size=2, budget_total=80000, transport="walk")
    skeletons = {n.reasons[i].replace(f"카페{i}", "X") for i in n.reasons}
    assert len(skeletons) == len(n.reasons)


def test_unknown_category_and_role_still_produce_a_sentence() -> None:
    odd = _stop(1, place("SOMETHING_NEW", "brand.new.category", 5000, name="새로운곳"), 10000)
    n = _service().template(_course([odd]), party_size=1, budget_total=20000, transport="car")
    assert n.reasons[1].startswith("오늘은 새로운곳") and "혼자서 10,000원" in n.reasons[1]


def test_tag_is_mentioned_only_when_the_purpose_likes_it() -> None:
    cafe = place("CAFE", "cafe", 6000, name="조용한카페", tags={"조용한": 1.0, "웨이팅있음": 0.9})
    course = _course([_stop(1, cafe, 12000), _stop(2, place("MEAL", name="밥집"), 20000)])
    svc = _service()
    assert "취향" not in svc.template(course, party_size=2, budget_total=50000, transport="walk").reasons[1]
    liked = svc.template(
        course, party_size=2, budget_total=50000, transport="walk", tag_affinity={"조용한": 0.8}
    )
    assert "'조용한' 취향에도 맞아요." in liked.reasons[1] and "웨이팅" not in liked.reasons[1]


def test_a_fact_tag_is_stated_as_a_fact_not_as_a_taste() -> None:
    """'관광공사 소개' 는 취향이 아니다 — "'관광공사 소개' 취향에도 맞아요" 라고 쓰면 어색하다."""
    meal = place("MEAL", "food.asian", 12000, name="옴산띠", tags={"관광공사 소개": 1.0})
    course = _course([_stop(1, meal, 24000), _stop(2, place("CAFE", "cafe", 6000, name="카페"), 12000)])
    out = _service().template(
        course, party_size=2, budget_total=50000, transport="walk", tag_affinity={"관광공사 소개": 0.6}
    )
    assert "한국관광공사가 소개한 곳이에요." in out.reasons[1]
    assert "'관광공사 소개' 취향" not in out.reasons[1]


def test_streamed_text_numbers_the_stops() -> None:
    text = _service().template(_four_stops(), party_size=2, budget_total=80000, transport="walk").as_text()
    lines = text.splitlines()
    assert lines[0].startswith("둘이서") and lines[1].startswith("① ") and lines[4].startswith("④ ")
    assert lines[-1].startswith("짠!")  # 14,000원 left → the tip


def test_pinning_v1_still_renders_for_a_rollback() -> None:
    loader = PromptLoader(get_prompt_loader()._dir, pins={"narrative_fallback": 1})
    n = _service(loader).template(_four_stops(), party_size=2, budget_total=80000, transport="walk")
    assert "코스에 넣기 좋아요" in n.reasons[1]
