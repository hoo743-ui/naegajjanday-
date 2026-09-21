"""동 · 읍 · 면 read from addresses: which token is the neighbourhood, and how wide its circle is."""

from __future__ import annotations

from typing import Any

from app.domain.models import GeoPoint
from app.infra.ingestion.bulk.common import load_json
from app.infra.ingestion.bulk.dongs import RULES_FILE, circle, dong_of, slug_for

RULES: dict[str, Any] = load_json(RULES_FILE)


def test_a_lot_address_names_its_dong_after_the_district() -> None:
    assert dong_of("서울특별시 금천구 가산동 60-3", RULES) == "가산동"
    assert dong_of("경기도 고양시 일산동구 백석동 1199-7", RULES) == "백석동"
    assert dong_of("충청남도 태안군 태안읍 남문리 629-2", RULES) == "태안읍"
    assert dong_of("강원특별자치도 강릉시 사천면 판교리 12", RULES) == "사천면"


def test_a_road_address_names_it_in_brackets() -> None:
    assert dong_of("서울특별시 영등포구 국회대로 26 (영등포동7가)", RULES) == "영등포동"
    assert dong_of("부산광역시 중구 해관로 65 (중앙동4가, 상가동)", RULES) == "중앙동"


def test_numbered_halves_are_the_name_people_say() -> None:
    assert dong_of("서울특별시 성동구 성수동2가 300-1", RULES) == "성수동"
    assert dong_of("서울특별시 종로구 종로1가 24", RULES) == "종로1가"
    assert dong_of("서울특별시 관악구 신림1동 10", RULES) == "신림동"


def test_what_follows_the_lot_number_is_a_building_not_a_neighbourhood() -> None:
    assert dong_of("서울특별시 중구 을지로 12 지하상가", RULES) is None
    assert dong_of("세종특별자치시 한누리대로 12-52", RULES) is None
    assert dong_of(None, RULES) is None and dong_of("", RULES) is None


def test_a_district_that_ends_like_a_dong_is_still_the_district() -> None:
    # 동구 · 중구 end in 구 and are skipped; the token after them is the neighbourhood
    assert dong_of("대구광역시 동구 신암동 1-37", RULES) == "신암동"


def test_the_circle_sits_on_the_median_and_ignores_the_outlier() -> None:
    spec = {"percentile": 0.85, "min_m": 400, "max_m": 1500}
    near = [GeoPoint(37.5 + i * 0.0005, 127.0 + i * 0.0005) for i in range(-10, 11)]
    centre, radius = circle([*near, GeoPoint(38.4, 128.2)], spec)
    assert abs(centre.lat - 37.5) < 0.001 and abs(centre.lng - 127.0) < 0.001
    assert 400 <= radius <= 1500
    tight = circle([GeoPoint(37.5, 127.0)] * 5, spec)
    assert tight[1] == 400  # never narrower than a walk around the block
    wide = circle([GeoPoint(37.5 + i * 0.01, 127.0) for i in range(20)], spec)
    assert wide[1] == 1500  # a 면 is 10 km across: the circle is where its places crowd, not its border


def test_the_slug_is_stable_ascii_and_tied_to_its_district() -> None:
    slug = slug_for("seoul-seongdong", "성수동")
    assert slug == slug_for("seoul-seongdong", "성수동")
    assert (
        slug.startswith("seoul-seongdong-d") and slug.isascii() and len(slug) == len("seoul-seongdong-d") + 6
    )
    assert slug != slug_for("seoul-gwangjin", "성수동")
