"""Bars filed as restaurants, sorted by their licence (docs/59 #14, app/infra/ingestion/bar_licence.py)."""

from __future__ import annotations

import pytest

from app.infra.ingestion.bar_licence import HOF, LIVE, LOUNGE, SOJU, Decision, decide


@pytest.mark.parametrize(
    ("origin", "kind", "name", "expected"),
    [
        # a drinking licence on a restaurant whose name says nothing: a bar, of the licence's kind
        ("food.korean", HOF, "좋은친구들", Decision("bar.pub")),
        ("food.korean", SOJU, "오늘도", Decision("bar.pocha")),
        ("food.korean", LOUNGE, "달빛동맹", Decision("bar")),
        ("food.korean", LIVE, "놀러와7080", Decision("bar")),
        # the name says the kind
        ("food.korean", HOF, "송쉐프포차", Decision("bar.pocha")),
        ("food.korean", SOJU, "느린마을양조장동탄 목동점", Decision("bar.makgeolli")),
        ("food.western", LOUNGE, "플럼위스키하우스", Decision("bar.cocktail")),
        ("food.korean", HOF, "오늘와인한잔", Decision("bar.wine")),
        # a Japanese kitchen that pours is an izakaya — unless the name says a meal
        ("food.japanese", HOF, "세이고우", Decision("bar.izakaya")),
        ("food.japanese", SOJU, "대림참치", Decision("food.japanese", drinks=True)),
        # the name says a meal: it stays a restaurant, and a family's meal does not go there
        ("food.korean", HOF, "강현숙왕족발", Decision("food.korean", drinks=True)),
        ("food.bbq", SOJU, "태영생막창", Decision("food.bbq", drinks=True)),
        # a strong-meal kind moves only when the name says bar
        ("food.chinese", HOF, "야래향", Decision("food.chinese", drinks=True)),
        ("food.chinese", HOF, "중식주점연", Decision("bar.pub")),
        # 호프/통닭: 치킨 is a chicken shop, 치킨호프 names its 호프
        ("food.korean", HOF, "교촌치킨 홍대점", Decision("food.korean", drinks=True)),
        ("food.korean", HOF, "자이치킨호프", Decision("bar.pub")),
        # 통닭(치킨) is not a drinking licence
        ("food.korean", "통닭(치킨)", "옛날통닭", Decision("food.korean")),
        # a café moves only when its name says bar
        ("cafe", HOF, "쥬씨프레소전남 화순점", Decision("cafe")),
        ("cafe", HOF, "금성호프", Decision("bar.pub")),
        ("cafe", HOF, "달빛커피호프", Decision("bar.pub")),
        ("cafe", LIVE, "보스라이브카페", Decision("bar")),
        ("cafe", LOUNGE, "카페라운지", Decision("cafe", drinks=True)),
        # every bar gets its kind; a 생맥주 (bar.pub) changes only when the name names another kind
        ("bar", None, "청춘포차", Decision("bar.pocha")),
        ("bar", None, "88야키토리", Decision("bar.izakaya")),
        ("bar", SOJU, "투타임", Decision("bar.pocha")),
        ("bar", None, "헤븐", Decision("bar")),
        ("bar.pub", None, "막내소주방", Decision("bar.pocha")),
        ("bar.pub", SOJU, "리베르", Decision("bar.pub")),
        ("bar.wine", None, "와인포차", Decision("bar.wine")),
        # not ours: other kinds of place keep their category
        ("activity.karaoke", HOF, "써니노래방", Decision("activity.karaoke")),
        ("food.korean", "한식", "우리포차", Decision("food.korean")),
    ],
)
def test_decide(origin: str, kind: str | None, name: str, expected: Decision) -> None:
    assert decide(origin, kind, name) == expected


def test_idempotent_on_its_own_output() -> None:
    """A place already moved decides the same from where it started (the rule keeps the origin)."""
    for origin, kind, name in (("food.korean", HOF, "좋은친구들"), ("bar", None, "청춘포차")):
        first = decide(origin, kind, name)
        assert decide(origin, kind, name) == first
        assert decide(first.category, kind, name).category == first.category
