"""docs/53: cinemas from the 영화상영관 standard data, and name-gated 소상공인 codes for 공방 · 방탈출 · 보드게임."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.domain.models import PlaceCandidate
from app.domain.recommendation.composer import FIXED_STAY_MIN, stay_minutes
from app.infra.ingestion import dedupe
from app.infra.ingestion.bulk import cinemas, delta, semas_store
from app.infra.ingestion.bulk.common import BulkPlace, load_json
from app.infra.ingestion.bulk.price_prior import PricePrior

RULES = {"exclude_kinds": ["자동차극장"], "exclude_name_keywords": ["이동상영"], "exclude_names": ["소극장"]}


def row(name: str, x: str = "193282.13", y: str = "450549.28", **extra: str) -> dict[str, str]:
    return {
        "개방자치단체코드": "3000000",
        "관리번호": extra.pop("id", name),
        "사업장명": name,
        "영업상태코드": extra.pop("status", "01"),
        "공연장형태구분명": extra.pop("kind", "영화관"),
        "좌표정보(X)": x,
        "좌표정보(Y)": y,
        "도로명주소": extra.pop("road", "서울특별시 마포구 양화로 176, 8층 (동교동)"),
        "지번주소": "",
        "전화번호": "",
        "인허가일자": "2003-02-12",
        **extra,
    }


# --- coordinates ---------------------------------------------------------------------------------


def test_epsg5174_converts_to_wgs84_within_metres() -> None:
    # 인디스페이스 (서울 마포구 양화로 176): registered TM point → the building on the map
    lat, lng = cinemas.tm5174_to_wgs84(193282.130799848, 450549.280167182)
    assert dedupe.distance_m(lat, lng, 37.55719, 126.92476) < 15
    # the false origin itself is 38°N on the modified central meridian (≈ 127.0029°E), shifted to WGS84
    lat0, lng0 = cinemas.tm5174_to_wgs84(200_000, 500_000)
    assert abs(lat0 - 38.0) < 0.01 and abs(lng0 - 127.0029) < 0.01


# --- names ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (["CGV상봉1관", "CGV상봉2관", "CGV상봉3관"], "CGV 상봉"),
        (["CGV거제 1관", "CGV거제 2관"], "CGV 거제"),  # the 제 of 거제 is not "제1관"
        (["CGV구로10제1관", "CGV구로10 제10관"], "CGV 구로"),  # a screen count is not the name
        (
            ["메가박스중앙(주) 구의이스트폴지점 DVA관", "메가박스중앙(주) 구의이스트폴지점 2관"],
            "메가박스 구의이스트폴",
        ),
        (
            ["롯데컬처웍스(주) 롯데시네마 건대입구관 (제4관)", "롯데시네마 건대입구관 (제5관)"],
            "롯데시네마 건대입구",
        ),
        (["씨지브이(주) 고양행신 제1관", "씨지브이(주) 고양행신 제2관"], "CGV 고양행신"),
        (["(주)써니트 수유지점 롯데시네마 수유", "(주)써니트 롯데시네마 수유"], "롯데시네마 수유"),
        (["메가박스 송파파크하비오점(9관)", "메가박스 송파파크하비오점(8관)"], "메가박스 송파파크하비오"),
        (["영양 작은영화관"], "영양 작은영화관"),  # "영화관" is never a screen
        (["임실한마당 작은별영화관(고추관)", "임실한마당 작은별영화관(치즈관)"], "임실한마당 작은별영화관"),
        (["씨네큐브광화문 1관", "씨네큐브광화문 2관"], "씨네큐브광화문"),
    ],
)
def test_screens_fold_into_one_named_theater(raw: list[str], expected: str) -> None:
    theaters = cinemas.read_theaters([row(n, id=str(i)) for i, n in enumerate(raw)], RULES)
    assert [t.name for t in theaters] == [expected]
    assert theaters[0].screens == len(raw)


def test_screen_only_rows_join_the_theater_or_take_the_neighbourhood() -> None:
    joined = cinemas.read_theaters(
        [row("CGV평택 2관", id="1"), row("CGV평택 3관", id="2"), row("CGV 3관", id="3")], RULES
    )
    assert [(t.name, t.screens) for t in joined] == [("CGV 평택", 3)]
    road = "서울특별시 강동구 천호옛길 85 (성내동)"
    alone = cinemas.read_theaters(
        [row("롯데시네마 1관", id="1", road=road), row("롯데시네마 2관", id="2", road=road)], RULES
    )
    assert [t.name for t in alone] == ["롯데시네마 성내동"]
    nameless = cinemas.read_theaters([row("1관", id="1"), row("2관", id="2")], RULES)
    assert nameless == []  # no brand, no name: we do not guess


def test_closed_drive_in_mobile_and_non_cinema_rows_are_left_out() -> None:
    rows = [
        row("폐업극장", status="03", x="1", y="1"),
        row("자동차극장", kind="자동차극장", x="2", y="2"),
        row("서울동화(이동상영관)", x="3", y="3"),
        row("케이엠티브이", x="4", y="4"),  # an office that registered a screen
        row("소극장", x="5", y="5"),
        row("낭만극장", x="6", y="6"),
    ]
    assert [t.name for t in cinemas.read_theaters(rows, RULES)] == ["낭만극장"]


def test_one_theater_in_two_buildings_is_one_place() -> None:
    rows = [
        row("메가박스 원주혁신점 1관", id="1", x="300000", y="400000"),
        row("메가박스 원주혁신점 2관", id="2", x="300000", y="400000"),
        row("메가박스 원주혁신점 6관", id="3", x="300050", y="400040"),
    ]
    theaters = cinemas.read_theaters(rows, RULES)
    assert [(t.name, t.screens) for t in theaters] == [("메가박스 원주혁신", 3)]
    assert theaters[0].external_id == "3000000-1"  # local-government code + 관리번호: unique nationwide


def test_cinema_place_price_and_duplicate_check() -> None:
    prior = PricePrior.from_data(load_json("price_prior.json"), load_json("regions_kr.json"))
    chain, indie = cinemas.read_theaters(
        [row("CGV홍대 1관", id="1"), row("낭만극장", id="2", x="190000", y="450000")], RULES
    )
    place = cinemas.to_place(chain, 37.55, 126.92, prior, "epsg5174")
    assert place.category_code == "activity.cinema" and place.price_is_estimated
    assert place.price_per_person == 15000  # the three chains: a weekend 2D ticket
    small = cinemas.to_place(indie, 37.55, 126.92, prior, "epsg5174")
    assert small.price_per_person == 10000
    same = dedupe.ExistingPlace(1, "CGV 홍대", 37.5502, 126.9201, None)
    far = dedupe.ExistingPlace(2, "CGV 홍대", 37.60, 126.92, None)
    assert cinemas.find_duplicate(place, [far, same]) is same
    assert cinemas.find_duplicate(place, [far]) is None


def test_delta_file_round_trips_and_says_it_is_complete(tmp_path: Path) -> None:
    place = BulkPlace(
        provider="std_cinema",
        external_id="x-1",
        name="CGV 홍대",
        category_code="activity.cinema",
        lat=37.55,
        lng=126.92,
        raw={"brand": "CGV"},
    )
    out = tmp_path / "cinemas.json"
    delta.write_delta(out, "std_cinema", [place], note="출처", complete=True)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["complete"] is True and data["provider"] == "std_cinema"
    assert delta._place(data["places"][0]) == place


# --- name gates ----------------------------------------------------------------------------------


def gate_mapper() -> semas_store.SemasMapper:
    prior = PricePrior.from_data(load_json("price_prior.json"), load_json("regions_kr.json"))
    categories = {"R10405": "activity.arcade", "I21201": "cafe"}
    return semas_store.SemasMapper.from_data(categories, load_json("bulk_rules.json"), prior)


def store(name: str, code: str) -> dict[str, str]:
    return {
        semas_store.COL_ID: name,
        semas_store.COL_NAME: name,
        semas_store.COL_CODE: code,
        semas_store.COL_SIDO: "서울특별시",
        semas_store.COL_LAT: "37.55",
        semas_store.COL_LNG: "126.92",
    }


@pytest.mark.parametrize(
    ("name", "code", "category"),
    [
        ("방탈출카페넥스트에디션건대", "R10405", "activity.escape"),  # moved out of 오락실
        ("키이스케이프강남", "R10499", "activity.escape"),
        ("보드게임카페레드버튼신촌", "R10405", "activity.boardgame"),
        ("홀덤에이스보드카페", "R10405", None),  # vetoed by the gate, dropped by the global list
        ("신순오락실", "R10405", "activity.arcade"),  # no gate matches: the code's own mapping
        ("성수향수공방아르브", "P10625", "activity.craft"),
        ("빚다도예공방", "P10613", "activity.craft"),
        ("다옴도예공방", "R10499", "activity.craft"),
        ("한국도예교육원", "P10613", None),  # a course-style academy is not a one-day class
        ("키즈아트공방", "P10625", None),
        ("커피공방느루", "P10625", None),
        ("은평요양보호사교육원", "P10625", None),
        ("진에듀", "P10501", None),
    ],
)
def test_name_gates_move_only_what_the_name_says(name: str, code: str, category: str | None) -> None:
    m = gate_mapper()
    r = store(name, code)
    got = m.category_for(r) if m.skip_reason(r) is None else None
    assert got == category


def test_a_moved_place_is_priced_as_what_it_is() -> None:
    m = gate_mapper()
    escape = m.build(store("비트포비아홍대", "R10405"))
    assert escape.category_code == "activity.escape" and escape.price_per_person == 22000


# --- a film lasts as long as it lasts -------------------------------------------------------------


def candidate(stay: int) -> PlaceCandidate:
    return PlaceCandidate(1, "p", "x", "activity.cinema", "ACTIVITY", 37.5, 127.0, default_stay_min=stay)


def test_a_show_keeps_its_length_whatever_the_window() -> None:
    assert stay_minutes(candidate(130), 0.5) == 130
    assert stay_minutes(candidate(130), 1.6) == 130
    assert stay_minutes(candidate(FIXED_STAY_MIN - 1), 0.5) == round((FIXED_STAY_MIN - 1) * 0.5)
    assert stay_minutes(candidate(60), 1.5) == 90


def test_seed_has_the_cinema_category_with_a_film_length() -> None:
    seed = json.loads((Path(__file__).parents[2] / "data" / "seed" / "categories.json").read_text("utf-8"))
    cat = next(c for c in seed["categories"] if c["code"] == "activity.cinema")
    assert cat["course_role"] == "ACTIVITY" and cat["default_stay_min"] >= FIXED_STAY_MIN
