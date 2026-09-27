"""docs/63 구경하는 가게: retail codes of the 소상공인 file let in by name — and what the page says about them."""

from __future__ import annotations

from datetime import datetime

import pytest

from app.domain.models import PlaceCandidate, Slot, Template
from app.domain.recommendation import shops as shop_lines
from app.domain.recommendation.option_text import parse_options
from app.evaluation import concept as C
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
    assert shop_lines.brand_of("카카오프렌즈플래그십스토어 홍대점") == (
        "shop.character",
        "카카오프렌즈 캐릭터",
    )
    assert shop_lines.brand_of("무신사스탠다드 성수점") == ("shop.select", "무신사")
    assert shop_lines.brand_of("성수빈티지") is None


@pytest.mark.parametrize(
    ("name", "code", "line"),
    [
        (
            "카카오프렌즈플래그십스토어 홍대점",
            "shop.character",
            "카카오프렌즈 캐릭터 플래그십 · 구경만 해도 20~30분",
        ),
        ("라인프렌즈 강남점", "shop.character", "라인프렌즈 캐릭터 매장 · 구경만 해도 20~30분"),
        ("무신사스탠다드 성수점", "shop.select", "무신사 매장 · 구경 20~30분"),
        ("성수빈티지", "shop.vintage", "빈티지 · 구제 가게 · 구경 30분 남짓"),
        ("모리소품샵", "shop.goods", "소품 · 문구 가게 · 구경 20분 남짓"),
    ],
)
def test_why_line_says_what_the_shop_is_and_nothing_more(name: str, code: str, line: str) -> None:
    got = shop_lines.why_line(name, code)
    assert got == line and len(got) <= 40
    assert "인기" not in got and "20대" not in got  # no claim the data does not hold


def test_age_taste_is_read_only_from_context_the_request_has() -> None:
    assert shop_lines.age_group("friends", None, anchored=True) == "20s"  # a campus day
    assert shop_lines.age_group("campus_food", None, anchored=False) == "20s"
    assert shop_lines.age_group("date", "new", anchored=False) == "20s"
    assert shop_lines.age_group("date", "anniversary", anchored=False) == "30s"
    assert shop_lines.age_group("friends", None, anchored=False) is None  # no age asked, none guessed
    assert shop_lines.taste_pull("travel", None, anchored=False) == {}
    pull = shop_lines.taste_pull("campus", None, anchored=False)
    assert pull["cat:shop.character"] > pull["cat:shop.select"] > 0
    assert max(pull.values()) <= 0.05  # a nudge, not a rule


def test_the_same_store_listed_twice_is_one() -> None:
    rows = [
        {"name": "라인프렌즈스퀘어성수", "lat": 37.5446, "lng": 127.0559},
        {"name": "라인프렌즈스퀘어 성수", "lat": 37.5447, "lng": 127.0560},
        {"name": "라인프렌즈스퀘어성수", "lat": 37.5600, "lng": 127.0559},  # 1.7 km away: another shop
    ]
    assert len(shops.dedupe_rows(rows, 150)) == 2


def test_is_shop() -> None:
    assert shop_lines.is_shop("shop") and shop_lines.is_shop("shop.vintage")
    assert not shop_lines.is_shop("shopping") and not shop_lines.is_shop("attraction.market")


@pytest.mark.parametrize(
    "text",
    [
        "성수 소품샵 구경하고 싶어",
        "빈티지샵 들렀다가 카페",
        "캐릭터샵 가고 싶어",
        "굿즈 사러 가자",
        "구제 쇼핑",
        "팝업 구경",
    ],
)
def test_a_shop_to_browse_is_the_shop_option_not_an_errand(text: str) -> None:
    got = parse_options(text)
    assert got.extras == ["SHOP"]
    assert got.errand is None  # "소품샵" is a kind of place, not a place to look up


def test_a_named_shop_is_still_an_errand() -> None:
    got = parse_options("라인프렌즈 들렀다가 저녁 먹자")
    assert got.errand is not None and got.errand.query == "라인프렌즈"
    assert got.extras == []


def test_declining_the_shops() -> None:
    assert parse_options("소품샵은 빼고 술 한잔").declined == ["SHOP"]


def _shop_record(
    stops: list[tuple[str, str, str, int, str | None]],
    extras: tuple[str, ...] = (),
    region: str = "seoul-seongsu",
) -> C.Record:
    case = C.Case(region, "friends", 3, 90000, "14:00", group="shop", extras=extras)
    return C.Record(
        case,
        stops=[
            C.Stop(
                i,
                role,
                "가게",
                cat,
                at,
                leave,
                0,
                5,
                kind="SHOPPING" if cat.startswith(("shop", "attraction.market")) else None,
                why=why,
            )
            for i, (role, cat, at, leave, why) in enumerate(stops, 1)
        ],
    )


def test_shop_metrics() -> None:
    off = _shop_record(
        [
            ("MEAL", "food.korean", "14:00", 900, None),
            ("ATTRACTION", "shop.vintage", "15:10", 945, "빈티지 · 구제 가게 · 구경 30분 남짓"),
        ]
    )
    plain = _shop_record([("MEAL", "food.korean", "14:00", 900, None), ("CAFE", "cafe", "15:10", 960, None)])
    asked = _shop_record([("ATTRACTION", "shop.goods", "20:40", 21 * 60 + 10, None)], extras=("SHOP",))
    twice = _shop_record(
        [
            ("ATTRACTION", "shop.goods", "14:00", 870, "x"),
            ("ATTRACTION", "attraction.market", "14:40", 900, None),
        ]
    )
    # 을지로: browsing is not its draw — a shop there unasked is counted against
    elsewhere = _shop_record(
        [("MEAL", "food.korean", "14:00", 900, None), ("ATTRACTION", "shop.goods", "15:10", 935, "x")],
        region="seoul-euljiro",
    )
    records = [off, plain, asked, twice, elsewhere]
    got = {r.id: r for r in C.evaluate_all(records)}
    assert got["shop_presence_rate"].value == pytest.approx(2 / 3, abs=1e-3)  # 성수: off, plain, twice
    assert got["shop_unasked_rate"].value == 1.0  # 을지로 alone
    assert got["shop_asked_rate"].value == 1.0
    assert got["shop_explained_rate"].value == pytest.approx(3 / 4, abs=1e-3)  # the asked one: no line
    assert got["shop_hours_violation_rate"].value == pytest.approx(1 / 4, abs=1e-3)  # past 21:00
    assert got["shop_twice_rate"].value == pytest.approx(1 / 5, abs=1e-3)
    # the base metrics never see the shop half
    assert got["mean_stops_day"].value is None
    assert all(c.half == "shop" for c in (r.case for r in records))


def test_the_shop_option_is_a_family_not_an_opt_in_category() -> None:
    from app.domain.recommendation.style import (
        category_matches,
        extra_roles,
        opt_in_categories,
        wanted_families,
    )

    assert extra_roles()["SHOP"]["family"] == "shop"
    assert "shop" in wanted_families()
    assert not any(c.startswith("shop") for c in opt_in_categories())  # shops come unasked too
    assert category_matches("shop.vintage", "shop") and category_matches("shop", "shop")
    assert not category_matches("attraction.market", "shop")
    assert category_matches("activity.cinema", "activity.cinema")
    assert not category_matches("activity.cinema.x", "activity.cinema")  # a category is not a family


def _template() -> Template:
    slots = (
        Slot(1, "MEAL", 0.6),
        Slot(2, "CAFE", 0.25),
        Slot(3, "ATTRACTION", 0.15),
    )
    return Template(1, "date_day", "date", "day", 10000, 2, 2, slots)


def test_an_afternoon_where_browsing_is_the_draw_gets_a_shops_only_slot_after_the_meal() -> None:
    day = datetime(2026, 10, 3, 13, 0)
    drawn = ("shop.select",)  # 성수 편집숍
    [t] = shop_lines.with_browse_slot([_template()], "date", day, drawn=drawn)
    assert [s.course_role for s in t.slots] == ["MEAL", "ATTRACTION", "CAFE", "ATTRACTION"]
    browse = t.slots[1]
    assert browse.family == "shop.select" and browse.is_optional and browse.budget_share == 0.0
    assert [s.position for s in t.slots] == [1, 2, 3, 4]
    assert t.slots[3].family is None  # the neighbourhood's own sight keeps its slot
    assert shop_lines.with_browse_slot([t], "date", day, drawn=drawn)[0] == t  # once
    assert shop_lines.with_browse_slot([t], "date", day, asked=True)[0] == t  # …asked or not
    # two kinds drawn: any shop
    [two] = shop_lines.with_browse_slot([_template()], "date", day, drawn=("shop.select", "shop.vintage"))
    assert two.slots[1].family == "shop"
    # not a family day, not the evening, not a trip
    assert shop_lines.with_browse_slot([_template()], "family", day, drawn=drawn)[0] == _template()
    assert (
        shop_lines.with_browse_slot([_template()], "date", day.replace(hour=19), drawn=drawn)[0]
        == _template()
    )


def test_no_browse_unasked_where_browsing_is_not_the_draw() -> None:
    """docs/59 #12: a shop near is not reason enough — only the option or the neighbourhood's draw."""
    day = datetime(2026, 10, 3, 13, 0)
    assert shop_lines.with_browse_slot([_template()], "date", day)[0] == _template()
    [asked] = shop_lines.with_browse_slot([_template()], "family", day.replace(hour=19), asked=True)
    assert asked.slots[1].family == "shop"  # asked: any purpose, any hour, any shop


def test_the_shop_draws_are_where_browsing_is_why_people_come() -> None:
    from app.domain.region_draws import shop_draw

    assert shop_draw("seoul-seongsu") == ("shop.select",)
    assert shop_draw("seoul-hongdae") == ("shop.character",)
    assert shop_draw("seoul-euljiro") == () and shop_draw("seoul-mangwon") == () and shop_draw(None) == ()


def _cand(pid: int, code: str) -> PlaceCandidate:
    return PlaceCandidate(pid, f"p{pid}", f"곳{pid}", code, "ATTRACTION", 37.5, 127.0)


def test_a_browse_slot_keeps_only_shops_and_empties_without_them() -> None:
    from app.domain.recommendation.budget import SlotBudget
    from app.domain.recommendation.style import family_pools

    browse = Slot(2, "ATTRACTION", 0.0, is_optional=True, family="shop")
    sight = Slot(3, "ATTRACTION", 0.15)
    pools = {
        2: [_cand(1, "attraction.street"), _cand(2, "shop.vintage"), _cand(3, "shop")],
        3: [_cand(1, "attraction.street"), _cand(2, "shop.vintage")],
    }
    got = family_pools(pools, [SlotBudget(browse, 0.0, 0.0), SlotBudget(sight, 0.15, 3000.0)])
    assert [c.id for c in got[2]] == [2, 3] and [c.id for c in got[3]] == [1, 2]
    none = family_pools({2: [_cand(1, "attraction.street")]}, [SlotBudget(browse, 0.0, 0.0)])
    assert none[2] == []  # an optional slot with an empty pool is dropped by the engine, silently
