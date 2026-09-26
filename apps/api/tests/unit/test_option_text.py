"""한 줄 말 → 코스 옵션 (docs/59 #2): the rule-based parser behind the result page's one-line input."""

from __future__ import annotations

import pytest

from app.domain.recommendation.option_text import ErrandAsk, option_label, parse_options
from app.domain.recommendation.style import extra_roles


def test_the_founders_example_is_a_shop_first_then_a_movie() -> None:
    got = parse_options("애플스토어 들렀다가 영화 보고 싶어")
    assert got.extras == ["MOVIE"]
    assert got.errand == ErrandAsk(query="애플스토어", when="before")
    assert got.conditions == [] and got.declined == []


@pytest.mark.parametrize(
    ("text", "extras"),
    [
        ("술 한잔 하고 싶어", ["BAR"]),
        ("끝나고 맥주 한 잔", ["BAR"]),
        ("혼술 가능한 곳", ["BAR"]),
        ("야구 보러 가자", ["BASEBALL"]),
        ("잠실 직관 가고 싶어", ["BASEBALL"]),
        ("CGV에서 영화 한 편", ["MOVIE"]),
        ("영화 보고 와인 한잔", ["MOVIE", "BAR"]),
    ],
)
def test_extras_are_read_in_the_order_they_were_said(text: str, extras: list[str]) -> None:
    assert parse_options(text).extras == extras


@pytest.mark.parametrize(
    "text",
    [
        "미술관 가고 싶어",  # 술 inside 미술 is not a drink
        "예술의전당 공연",
        "커피 한잔 하자",  # a coffee is not a bar
        "녹차 한 잔 마시고 산책",
        "비싼 데는 싫어",  # 비 of 비싼 is not rain
    ],
)
def test_words_that_only_look_like_an_option_are_ignored(text: str) -> None:
    got = parse_options(text)
    assert got.extras == [] and got.conditions == []


@pytest.mark.parametrize(
    "text", ["비 온대", "비가 와서 실내로", "비 오는 날이야", "우산 챙겨야 하는 날", "실내 위주로"]
)
def test_rain_is_a_condition(text: str) -> None:
    got = parse_options(text)
    assert got.conditions == ["rain"] and got.extras == []


def test_declining_takes_an_option_off() -> None:
    got = parse_options("술은 빼고 영화 말고 야구")
    assert got.declined == ["BAR", "MOVIE"]
    assert got.extras == ["BASEBALL"]


def test_errand_after_the_day_when_said_after_it_ends() -> None:
    got = parse_options("영화 보고 끝나고 다이소 들를래")
    assert got.extras == ["MOVIE"]
    assert got.errand == ErrandAsk(query="다이소", when="after")


@pytest.mark.parametrize(
    ("text", "query"),
    [
        ("오늘 먼저 올리브영 들렀다가 놀자", "올리브영"),
        ("스타벅스 리저브 잠깐 들르고", "스타벅스 리저브"),
        ("밥 먹고 교보문고에 들렀다가 한잔", "교보문고"),
        ("친구랑 애플 가로수길 들러서 카페", "애플 가로수길"),
    ],
)
def test_the_place_name_stops_at_words_that_are_not_a_name(text: str, query: str) -> None:
    errand = parse_options(text).errand
    assert errand is not None and errand.query == query and errand.when == "before"


def test_a_place_that_is_itself_an_option_is_not_an_errand() -> None:
    got = parse_options("야구장 갔다가 치맥")
    assert got.errand is None
    assert got.extras == ["BASEBALL", "BAR"]


def test_nothing_known_is_empty_and_never_raises() -> None:
    for text in ["", "   ", "그냥 좋은 데", "?!~"]:
        assert parse_options(text).empty


def test_every_extra_the_parser_can_name_is_one_the_engine_knows() -> None:
    from app.domain.recommendation.option_text import phrase_rules

    for rule in phrase_rules().options:
        if rule.kind == "extra":
            assert rule.key in extra_roles()
        assert option_label(rule.key)
