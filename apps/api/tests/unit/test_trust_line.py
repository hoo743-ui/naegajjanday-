"""믿을 이유 한 줄 (docs/59 #15): stored facts only, strongest first, nothing where there is nothing."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

from app.domain.trust import (
    BANNED_WORDS,
    LINE_MAX,
    TrustFact,
    TrustFacts,
    TrustLine,
    for_place,
    grounded,
    trust_facts,
    trust_line,
)
from app.evaluation import concept as C
from tests.factories import place

TODAY = date(2026, 10, 3)


def test_designation_leads_and_licence_years_follow() -> None:
    p = place("MEAL", tags={"모범음식점": 1.0})
    line, evidence = for_place(p, TrustFacts(licence_on=date(1992, 5, 1)), today=TODAY, area="망원동")
    assert line is not None
    assert line.kind == "designated"
    # the card: one fact, in compact words; the sheet keeps the full words
    assert line.text == "모범음식점"
    assert [f.kind for f in line.facts] == ["designated", "long_run"]
    assert [f.text for f in line.facts] == ["지자체 지정 모범음식점", "1992년부터 34년째 영업"]
    assert line.facts[1].short == "34년째 영업"
    assert grounded(line, evidence, today=TODAY)


def test_provider_rows_count_as_designations() -> None:
    p = place("MEAL")
    facts = TrustFacts(providers=frozenset({"goodprice", "centurystore"}), menu_name="칼국수", menu_price=9000,
                       menu_source="goodprice")  # fmt: skip
    line, evidence = for_place(p, facts, today=TODAY, area=None)
    assert line is not None
    assert [f.text for f in line.facts][:3] == ["중기부 지정 백년가게", "착한가격업소", "칼국수 9,000원"]
    assert line.facts[2].source == "행정안전부 착한가격업소 조사 가격"
    assert grounded(line, evidence, today=TODAY)


def test_draw_visit_rank_and_photos_in_that_order() -> None:
    p = place("MEAL", name="또또칼국수")
    p.local_word, p.local_draw = "칼국수", True
    facts = TrustFacts(visit_rank=12, visit_area="서울 마포구", visit_month="202608", photos=3)
    line, evidence = for_place(p, facts, today=TODAY, area="망원동")
    assert line is not None
    assert [f.text for f in line.facts] == [
        "망원동 명물 칼국수",
        "마포구 티맵 목적지 12위",
        "확인된 사진 3장",
    ]
    assert line.facts[1].source == "티맵 내비게이션 목적지 실측 (2026년 8월)"
    assert line.text == "망원동 명물 칼국수"
    assert [f.short for f in line.facts] == ["망원동 명물 칼국수", "티맵 목적지 12위", "사진 3장"]
    assert grounded(line, evidence, today=TODAY)


def test_a_specialty_guessed_from_signs_is_not_said() -> None:
    p = place("MEAL", name="홍대칼국수")
    p.local_word, p.local_draw = "칼국수", False  # region_signature statistics, not draws.json
    assert for_place(p, None, today=TODAY, area="홍대")[0] is None


def test_nothing_stored_means_no_line() -> None:
    assert for_place(place("MEAL"), None, today=TODAY, area="홍대")[0] is None
    assert for_place(place("MEAL"), TrustFacts(), today=TODAY, area="홍대")[0] is None
    # a young licence, a rank past the top 30: not a reason
    weak = TrustFacts(licence_on=date(2024, 1, 1), visit_rank=31, visit_area="마포구")
    assert for_place(place("MEAL"), weak, today=TODAY, area="홍대")[0] is None
    # a photo alone is a (weak) fact, and it is said as a count only
    line = for_place(place("MEAL"), TrustFacts(photos=2), today=TODAY, area=None)[0]
    assert line is not None and line.text == "사진 2장" and line.facts[0].text == "확인된 사진 2장"


def test_menu_names_that_would_make_a_claim_are_skipped() -> None:
    facts = TrustFacts(menu_name="인기세트", menu_price=12000, menu_source="goodprice")
    assert for_place(place("MEAL"), facts, today=TODAY, area=None)[0] is None


def test_events_get_no_line() -> None:
    p = place("EVENT", "culture.festival", None, is_event=True, tags={"관광공사 소개": 1.0})
    assert trust_facts(p, TrustFacts(photos=3), today=TODAY) == []


def test_every_line_the_rules_can_make_is_grounded() -> None:
    """trust_invented_rate = 0 by construction: every fact reads a field the place has."""
    p = place("MEAL", tags={"관광공사 소개": 1.0, "백년가게": 1.0, "모범음식점": 1.0})
    p.local_word, p.local_draw = "순대", True
    facts = TrustFacts(
        providers=frozenset({"goodprice", "tourapi"}),
        licence_on=date(1978, 3, 2),
        visit_rank=1,
        visit_area="강원 속초시",
        visit_month="202608",
        menu_name="순대국",
        menu_price=8000,
        menu_source="goodprice",
        photos=4,
    )
    line, evidence = for_place(p, facts, today=TODAY, area="속초 중앙시장")
    assert line is not None
    assert grounded(line, evidence, today=TODAY)
    assert not any(w in f.text for f in line.facts for w in BANNED_WORDS)


def test_invented_facts_are_caught() -> None:
    p = place("MEAL", tags={"모범음식점": 1.0})
    line, evidence = for_place(p, TrustFacts(licence_on=date(1992, 5, 1)), today=TODAY, area=None)
    assert line is not None
    # a claim word
    assert not grounded(replace(line, text="인기 많은 곳"), evidence, today=TODAY)
    # a fact whose field the place does not have
    fake = TrustFact(
        "designated", "중기부 지정 백년가게", "중소벤처기업부 백년가게 지정", "place_tag:백년가게"
    )
    assert not grounded(TrustLine(fake.text, fake.kind, fake.source, (fake,)), evidence, today=TODAY)
    # a number that is not in the field
    wrong = TrustFact(
        "long_run", "1980년부터 46년째 영업", "지자체 인허가(영업 신고) 기록", "place_source:lic.인허가일자"
    )
    assert not grounded(TrustLine(wrong.text, wrong.kind, wrong.source, (wrong,)), evidence, today=TODAY)
    # a card line that is not made of its facts
    assert not grounded(replace(line, text="지자체 지정 모범음식점 · 줄 서는 집"), evidence, today=TODAY)


def test_line_keeps_to_one_short_fact() -> None:
    long_area = "아주아주아주아주아주긴이름의동네골목상권"
    p = place("MEAL")
    p.local_word, p.local_draw = "칼국수", True
    found = trust_facts(p, TrustFacts(), today=TODAY, area=long_area, draw_word="칼국수")
    line = trust_line(found)
    assert line is not None and line.text is not None and len(line.text) <= LINE_MAX
    assert line.text == "동네 명물 칼국수"  # a long neighbourhood name stays on the sheet
    assert found[0].text == f"{long_area} 명물 칼국수"


def test_tourapi_listing_is_the_weakest_fact() -> None:
    """docs/59 #21: "관광공사 관광정보에 실린 곳" goes after years, a draw, a menu price, a Tmap rank and photos."""
    p = place("MEAL", tags={"관광공사 소개": 1.0})
    line = for_place(p, TrustFacts(photos=2), today=TODAY, area=None)[0]
    assert line is not None and line.text == "사진 2장"
    assert [f.short for f in line.facts] == ["사진 2장", "관광공사 소개"]
    # alone, it still says something — in two words
    alone = for_place(p, None, today=TODAY, area=None)[0]
    assert alone is not None and alone.text == "관광공사 소개"
    assert alone.facts[0].text == "관광공사 관광정보에 실린 곳"
    # a strong designation still leads
    strong = for_place(
        place("MEAL", tags={"관광공사 소개": 1.0, "백년가게": 1.0}), None, today=TODAY, area=None
    )[0]
    assert strong is not None and strong.text == "백년가게"


def test_a_course_never_says_the_same_card_words_twice() -> None:
    p = place("MEAL", tags={"관광공사 소개": 1.0})
    first, ev = for_place(p, TrustFacts(photos=2), today=TODAY, area=None)
    assert first is not None and first.text == "사진 2장"
    second, ev2 = for_place(p, TrustFacts(photos=2), today=TODAY, area=None, taken={"사진 2장"})
    assert second is not None and second.text == "관광공사 소개"  # the next-best fact
    third, ev3 = for_place(
        p, TrustFacts(photos=2), today=TODAY, area=None, taken={"사진 2장", "관광공사 소개"}
    )
    # nothing new to say: no card line, but the sheet keeps every fact
    assert third is not None and third.text is None and len(third.facts) == 2
    assert all(grounded(ln, e, today=TODAY) for ln, e in ((first, ev), (second, ev2), (third, ev3)))


def test_a_second_place_with_its_own_same_fact_says_it_differently() -> None:
    """Two gelato shops of 성수, two places licensed the same year: their own facts, worded a second way —
    a label many places share (관광공사 소개 · 사진 N장) gets no second wording."""
    p = place("DESSERT", name="마망젤라또")
    p.local_word, p.local_draw = "젤라또", True
    line, ev = for_place(p, None, today=TODAY, area="성수", taken={"성수 명물 젤라또"})
    assert line is not None and line.text == "여기도 성수 명물 젤라또"
    assert grounded(line, ev, today=TODAY)
    old = TrustFacts(licence_on=date(1995, 1, 1))
    line, ev = for_place(place("BAR"), old, today=TODAY, area=None, taken={"31년째 영업"})
    assert line is not None and line.text == "1995년부터 31년째 영업"
    assert grounded(line, ev, today=TODAY)
    assert not grounded(replace(line, text="여기도 31년째 영업"), ev, today=TODAY)


def test_scorecard_flags_a_course_that_repeats_a_line() -> None:
    def s(trust: str | None, position: int) -> C.Stop:
        return C.Stop(position=position, role="MEAL", name=str(position), category="food.korean", at="12:00",
                      leave_min=13 * 60, price=10000, leg=5, trust=trust)  # fmt: skip

    case = C.Case("seoul-hongdae", "date", 2, 60000, "12:00", group="hotspot")
    twice = C.Record(case, price=1, stops=[s("관광공사 소개", 1), s("관광공사 소개", 2)])
    once = C.Record(case, price=1, stops=[s("관광공사 소개", 1), s("34년째 영업", 2), s(None, 3)])
    single = C.Record(case, price=1, stops=[s("관광공사 소개", 1)])  # one line: not counted
    got = C.evaluate(C.METRIC_BY_ID["trust_repeat_rate"], [twice, once, single])
    assert got.value == 0.5 and not got.passed


def test_scorecard_counts_food_stops_with_a_line_and_invented_ones() -> None:
    def s(role: str, trust: str | None, ok: bool = True, position: int = 1) -> C.Stop:
        return C.Stop(position=position, role=role, name=role, category="food.korean", at="12:00",
                      leave_min=13 * 60, price=10000, leg=5, trust=trust, trust_ok=ok)  # fmt: skip

    case = C.Case("seoul-hongdae", "date", 2, 60000, "12:00", group="hotspot")
    good = C.Record(case, price=1, stops=[s("MEAL", "지자체 지정 모범음식점"), s("CAFE", None, position=2),
                                           s("ATTRACTION", None, position=3)])  # fmt: skip
    bad = C.Record(case, price=1, stops=[s("BAR", "인기 많은 곳", ok=False)])
    line = C.evaluate(C.METRIC_BY_ID["trust_line_rate"], [good, bad])
    assert line.value == round(2 / 3, 4)  # MEAL ✓ · CAFE ✗ · BAR ✓ — the sight is not counted
    invented = C.evaluate(C.METRIC_BY_ID["trust_invented_rate"], [good, bad])
    assert invented.value == 0.5 and not invented.passed


def test_a_neighbourhood_name_with_a_number_is_not_an_invented_number() -> None:
    """익선동·종로3가: the scorecard's first run flagged "3" as a number no field held (a false alarm)."""
    p = place("MEAL", name="종로빈대떡")
    p.local_word, p.local_draw = "빈대떡", True
    line, evidence = for_place(p, TrustFacts(licence_on=date(1998, 1, 1)), today=TODAY, area="익선동·종로3가")
    assert line is not None and line.text == "28년째 영업"
    assert line.facts[1].text == "익선동·종로3가 명물 빈대떡"
    assert grounded(line, evidence, today=TODAY)
    # without the area on record, the same "3" is a number from nowhere
    assert not grounded(line, {k: v for k, v in evidence.items() if k != "region.name"}, today=TODAY)
