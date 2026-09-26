"""docs/62 구경하는 가게: retail codes of the 소상공인 file let in by name — and what the page says about them."""

from __future__ import annotations

import pytest

from app.infra.ingestion.bulk import semas_store, shops
from app.infra.ingestion.bulk.common import load_json
from app.infra.ingestion.bulk.price_prior import PricePrior


def shop_mapper() -> semas_store.SemasMapper:
    prior = PricePrior.from_data(load_json("price_prior.json"), load_json("regions_kr.json"))
    return semas_store.SemasMapper.from_data(
        {"I21201": "cafe"}, load_json("bulk_rules.json"), prior, extra_gates=shops.gates()
    )


def store(name: str, code: str, branch: str = "") -> dict[str, str]:
    return {
        semas_store.COL_ID: name,
        semas_store.COL_NAME: name,
        semas_store.COL_BRANCH: branch,
        semas_store.COL_CODE: code,
        semas_store.COL_SIDO: "서울특별시",
        semas_store.COL_LAT: "37.55",
        semas_store.COL_LNG: "126.92",
    }


@pytest.mark.parametrize(
    ("name", "code", "category"),
    [
        ("카카오프렌즈플래그십스토어", "G21306", "shop.character"),  # a brand: a destination of its own
        ("라인프렌즈스퀘어성수", "G21306", "shop.character"),
        ("애니메이트", "G21306", "shop.character"),
        ("모모가챠홍대상수점", "G21306", "shop.character"),
        ("짱구마트", "G21306", None),  # 짱구 alone is a nickname, not the character shop
        ("디즈니골프", "G20905", None),  # golf wear, not Disney
        ("뽑기프렌즈", "G21306", None),  # a claw-machine room
        ("성수빈티지", "G20905", "shop.vintage"),
        ("구제나라", "G22201", "shop.vintage"),
        ("대구제일교회", "G22201", None),  # '구제' inside '대구제일'
        ("동서가구제2매장", "G22201", None),
        ("중고명품하이앤바이", "G22201", None),
        ("서울레코드", "G21303", "shop.vintage"),
        ("무신사스탠다드", "G20905", "shop.select"),
        ("와키윌리성수플래그십", "G20905", "shop.select"),
        ("올리브영명동플래그십", "G22199", None),  # a cosmetics chain's flagship is still the chain
        ("레노마홈플래그십스토어", "G20906", None),  # a code not looked in
        ("모리소품샵", "G21802", "shop.goods"),
        ("다람쥐잡화점", "G21802", "shop.goods"),
        ("바다위구름상점", "G21802", "shop.goods"),  # 기념품점 code: '상점' is enough
        ("바다위구름상점", "G21302", None),  # …but not in a stationery code
        ("서울공예사", "G21802", None),
        ("송백표구화랑", "G21802", None),
        ("아트박스홍대점", "G21302", "shop.goods"),
        ("알파문구", "G21302", None),  # a school stationery shop is not a place to browse
        ("신세계아미팝업", "G20905", None),  # a pop-up: gone before the next file
        ("씨제이올리브영홍대입구역점", "G22199", None),
        ("빈티지편집샵", "G20905", "shop.vintage"),  # the first kind that matches
    ],
)
def test_only_what_the_name_says_is_a_shop(name: str, code: str, category: str | None) -> None:
    m = shop_mapper()
    r = store(name, code)
    got = m.category_for(r) if m.skip_reason(r) is None else None
    assert got == category


def test_a_shop_is_not_priced_and_keeps_its_sign() -> None:
    place = shop_mapper().build(store("무신사무신사스탠다드", "G20905", branch="성수점"))
    assert place.category_code == "shop.select"
    assert place.name == "무신사스탠다드 성수점"  # the company in front is dropped
    assert place.price_per_person is None and not place.price_is_estimated


@pytest.mark.parametrize(
    ("name", "want"),
    [
        ("무신사무신사스탠다드", "무신사스탠다드"),
        ("무신사무신사", "무신사"),
        ("하하하하호프", "하하하하호프"),  # two-letter repeats are names people choose
        ("라인프렌즈", "라인프렌즈"),
    ],
)
def test_undoubled(name: str, want: str) -> None:
    assert semas_store.undoubled(name) == want


def test_a_place_that_is_not_a_shop_keeps_its_name() -> None:
    assert semas_store.display_name("무신사무신사", "", "cafe") == "무신사무신사"


def test_brand_of() -> None:
    assert shops.brand_of("카카오프렌즈플래그십스토어 홍대점") == ("shop.character", "카카오프렌즈 캐릭터")
    assert shops.brand_of("무신사스탠다드 성수점") == ("shop.select", "무신사")
    assert shops.brand_of("성수빈티지") is None


def test_the_same_store_listed_twice_is_one() -> None:
    rows = [
        {"name": "라인프렌즈스퀘어성수", "lat": 37.5446, "lng": 127.0559},
        {"name": "라인프렌즈스퀘어 성수", "lat": 37.5447, "lng": 127.0560},
        {"name": "라인프렌즈스퀘어성수", "lat": 37.5600, "lng": 127.0559},  # 1.7 km away: another shop
    ]
    assert len(shops.dedupe_rows(rows, 150)) == 2


def test_is_shop() -> None:
    assert shops.is_shop("shop") and shops.is_shop("shop.vintage")
    assert not shops.is_shop("shopping") and not shops.is_shop("attraction.market")
