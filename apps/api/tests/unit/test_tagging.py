from __future__ import annotations

import json
from pathlib import Path

from app.core.config import API_ROOT
from app.domain.recommendation.features import purpose_fit
from app.infra.tagging import TagRules, get_tag_rules, merge_tags

PURPOSES = {
    p["code"]: p["tag_affinities"]
    for p in json.loads((API_ROOT / "data" / "seed" / "purposes.json").read_text(encoding="utf-8"))[
        "purposes"
    ]
}


def _tags(category: str, name: str, role: str = "MEAL", measured: bool = False) -> dict[str, float]:
    return get_tag_rules().derive(
        category_code=category, name=name, course_role=role, has_measured_price=measured
    )


def test_category_rules_stack_from_general_to_specific() -> None:
    view = _tags("cafe.view", "어느 카페", "CAFE")
    assert view["뷰맛집"] == 1.0 and view["실내"] == 0.5  # "cafe" base + "cafe.view" on top
    assert _tags("cafe.unknown_child", "어느 카페", "CAFE") == _tags("cafe", "어느 카페", "CAFE")
    assert _tags("brand.new", "새로운곳") == {}


def test_name_rules_and_chains() -> None:
    assert _tags("cafe", "루프탑 카페 하늘", "CAFE")["뷰맛집"] == 0.9
    assert _tags("food.korean", "할매 국밥")["혼밥OK"] == 0.8
    assert "체인점" in _tags("cafe", "스타벅스 강남R점", "CAFE")
    assert "체인점" in _tags("cafe", "메가엠지씨커피 신촌점", "CAFE")
    assert "체인점" not in _tags("cafe", "동네 로스터리", "CAFE")
    rules = get_tag_rules()
    assert "체인점" not in rules.visible(_tags("cafe", "스타벅스", "CAFE"))  # scoring only, never on a card


def test_a_grill_is_not_a_group_hall_unless_its_sign_says_so() -> None:
    """단체석 ≥ 0.8 means '단체석 위주' — the date's never (docs/48 §1). The category alone can't tell."""
    assert 0 < _tags("food.bbq", "흑돼지생고기")["단체석"] < 0.8  # seats a group; not a 회식 hall
    assert _tags("food.bbq", "OO갈비 단체회식")["단체석"] >= 0.8
    assert _tags("food.korean", "OO연회장")["단체석"] >= 0.8
    assert _tags("food.bbq", "무한리필 고기")["단체석"] >= 0.8


def test_measured_price_marks_good_price_shops_only_for_food_roles() -> None:
    assert _tags("food.korean", "삼삼뚝배기", measured=True)["착한가격업소"] == 1.0
    assert "착한가격업소" not in _tags("food.korean", "삼삼뚝배기", measured=False)
    assert "착한가격업소" not in _tags(
        "culture.museum", "어느 박물관", "CULTURE", measured=True
    )  # a ticket price


def test_stored_tags_win_over_derived_ones() -> None:
    assert merge_tags({"조용한": 0.1}, {"조용한": 0.9, "아늑한": 0.4}) == {"조용한": 0.1, "아늑한": 0.4}


def test_the_same_places_rank_differently_per_purpose() -> None:
    """The point of the whole exercise: before tags, every purpose scored every place 0.5."""
    wine_bar = _tags("bar.wine", "르뱅 와인바", "BAR")
    pocha = _tags("bar.pocha", "한신포차 홍대점", "BAR")
    noodle = _tags("food.noodle", "할매 칼국수")
    chain_cafe = _tags("cafe", "스타벅스 홍대역점", "CAFE")
    indie_cafe = _tags("cafe.roastery", "연남 로스터리", "CAFE")
    park = _tags("attraction.park", "연남동 경의선숲길", "ATTRACTION")

    def fit(purpose: str, tags: dict[str, float]) -> float:
        return purpose_fit(tags, PURPOSES[purpose])

    assert fit("date", wine_bar) > 0.8 > fit("date", pocha)
    assert fit("friends", pocha) > fit("friends", wine_bar)
    assert fit("solo", noodle) > 0.8 and fit("solo", noodle) > fit("date", noodle)
    assert fit("date", indie_cafe) > fit("date", chain_cafe)  # a date should not end up at a chain
    assert fit("travel", indie_cafe) > fit("travel", chain_cafe)
    assert fit("solo", chain_cafe) >= fit("date", chain_cafe)  # predictable is fine when alone
    assert fit("family", park) > 0.75
    for purpose in PURPOSES:  # nothing is neutral any more for the common categories
        assert fit(purpose, wine_bar) != 0.5 or fit(purpose, pocha) != 0.5


def test_missing_rules_file_means_no_tags(tmp_path: Path) -> None:
    rules = TagRules()
    assert rules.derive(category_code="cafe", name="x", course_role="CAFE", has_measured_price=True) == {}


def test_company_names_are_unlisted_but_playful_shop_names_are_not() -> None:
    rules = get_tag_rules()
    for name in (
        "티에스리테일",
        "하이푸드",
        "엔제이푸드",
        "다락에프앤비",
        "올댓플러스F&B",
        "혜원출판사",
        "하이푸드 홍대점",
    ):
        assert rules.is_unlisted(name), name
    for name in (
        "홍대쌀국수",
        "해물면사무소",
        "닭발상사",
        "달빛물산",
        "커피컴퍼니",
        "바다씨푸드",
        "스타벅스 홍대역점",
    ):
        assert not rules.is_unlisted(name), name


def test_sign_name_drops_a_company_prefix_but_not_a_real_brand() -> None:
    rules = get_tag_rules()
    assert rules.sign_name("강남에프앤비화덕고깃간 역삼본점") == "화덕고깃간 역삼본점"
    assert rules.sign_name("에스앤에스컴퍼니서가앤쿡홍대EXIT점") == "서가앤쿡홍대EXIT점"
    assert rules.sign_name("커피컴퍼니 홍대점") == "커피컴퍼니 홍대점"  # 뒤가 지점 표기뿐 → 그대로
    assert rules.sign_name("홍대쌀국수") == "홍대쌀국수"


def test_place_listed_by_the_tourism_organization_gets_a_trust_tag() -> None:
    rules = get_tag_rules()
    common = {
        "category_code": "food.korean",
        "name": "장터설렁탕",
        "course_role": "MEAL",
        "has_measured_price": False,
    }
    listed = rules.derive(**common, photo_url="https://tong.visitkorea.or.kr/cms/resource/1/a.jpg")
    assert listed["관광공사 소개"] == 1.0
    assert "관광공사 소개" not in rules.derive(**common, photo_url=None)
    assert "관광공사 소개" not in rules.derive(**common, photo_url="https://upload.wikimedia.org/x.jpg")
