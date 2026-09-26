"""Backlog 6: place names the SEMAS file joined with ";". Every case is a real row of the local DB (2026-09-26)."""

from __future__ import annotations

import pytest

from app.infra.ingestion.bulk.semas_store import display_name as semas_display_name
from app.infra.ingestion.place_names import display_name


@pytest.mark.parametrize(
    ("name", "category", "shown"),
    [
        # several businesses at one address → the first, or the one the place is filed as
        ("신의주찹쌀순대;황소곱창;장충왕족발", "food.korean", "신의주찹쌀순대"),
        ("무봉리순대국;원당감자탕;황제왕갈비탕", "food.korean", "무봉리순대국"),
        ("원콜전자;오백냥노래연습실", "activity.karaoke", "오백냥노래연습실"),
        ("거제에이치-애비뉴(몽돌비치);하와이노래연습장", "activity.karaoke", "하와이노래연습장"),
        ("로얄노래방;모텔", "activity.karaoke", "로얄노래방"),
        ("스타게임장;노래연습장", "activity.karaoke", "스타게임장"),  # a bare "노래연습장" is not a name
        ("카페에스토;문래동부동산공인중개사사무소", "cafe", "카페에스토"),
        ("풍기인삼직판장;더바른토스트", "food.brunch", "더바른토스트"),
        # a name and its menu → the name
        ("잭아저씨족발;보쌈", "food.korean", "잭아저씨족발"),
        ("청와삼대족발;보쌈;칼국수", "food.korean", "청와삼대족발"),
        ("팔천순대;곱창", "food.korean", "팔천순대"),
        # the branch written after the last part stays
        ("담소소사골순대;육개장 문정점", "food.korean", "담소소사골순대 문정점"),
        ("흥부찜닭;공수간;삼겹본능 신림점", "food.korean", "흥부찜닭 신림점"),
        ("찬이네칼국수;팥죽 전문점", "food.noodle", "찬이네칼국수"),  # "전문점" is not a branch
        ("뚜레쥬르;고구마명가영남대 병원점", "dessert.bakery", "뚜레쥬르"),
        # a comma inside one name comes back (the licence data writes "지금,여기", "카페,메쥬")
        ("지금;여기", "bar", "지금,여기"),
        ("카페;메쥬", "cafe", "카페,메쥬"),
        ("셀프사진관예뻐서;봄 동탄점", "activity.photo", "셀프사진관예뻐서,봄 동탄점"),
        ("1;2;3게임장", "activity.arcade", "1,2,3게임장"),
        ("3;6;9코인노래연습장", "activity.karaoke", "3,6,9코인노래연습장"),
        ("10;000원의행복", "food.korean", "10,000원의행복"),
        ("을지로뚝배기오리탕9;900원", "food.korean", "을지로뚝배기오리탕9,900원"),
        ("뮤즈노래타운1;2;3", "activity.karaoke", "뮤즈노래타운1,2,3"),
        # a list in brackets is a note
        ("식사이어티(풍국면;본죽앤비빔밥카페;구슬함박;버거룰)", "food.western", "식사이어티"),
        ("로즈까페(커피;호프;맥", "cafe", "로즈까페"),
        # nothing to do
        ("성수 연방", "cafe", "성수 연방"),
    ],
)
def test_display_name(name: str, category: str, shown: str) -> None:
    assert display_name(name, category) == shown
    assert display_name(shown, category) == shown  # idempotent: a second pass changes nothing


def test_semas_rows_are_named_at_ingestion() -> None:
    assert semas_display_name("신의주찹쌀순대;황소곱창;장충왕족발", "", "food.korean") == "신의주찹쌀순대"
    assert (
        semas_display_name("셀프사진관예뻐서;봄", "동탄점", "activity.photo") == "셀프사진관예뻐서,봄 동탄점"
    )
    assert semas_display_name("커피빈홍대역8번출구점", "코리아") == "커피빈홍대역8번출구점"
