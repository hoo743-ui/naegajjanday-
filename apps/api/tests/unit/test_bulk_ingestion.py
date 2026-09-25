"""Bulk path (nationwide public files): parsers, mappers, price prior, regions, dedupe, idempotent upsert.

Tiny inline CSV fixtures only — nothing here touches the network or the real data files.
"""

from __future__ import annotations

import io
import zipfile
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.core.config import API_ROOT, Settings
from app.infra.db.models import Event, MenuItem, OpeningHour, Place, PlaceSource, PlaceStats, Region
from app.infra.db.session import Database
from app.infra.ingestion import dedupe
from app.infra.ingestion.bulk import goodprice, runner, semas_store, std_datasets
from app.infra.ingestion.bulk.common import BulkReport, GridIndex, iter_csv, load_json, sniff_encoding
from app.infra.ingestion.bulk.download import load_sources, manual_steps, parse_detail_pk, rows_to_csv
from app.infra.ingestion.bulk.price_prior import PricePrior
from app.infra.ingestion.bulk.regions import (
    PointCloud,
    RegionStats,
    build_region_rows,
    dense_center,
    percentile_radius,
    romanize,
    sigungu_slug,
)
from app.infra.ingestion.config_loader import load_config

BOM = chr(0xFEFF)  # UTF-8 byte-order mark, as in the real files
SEMAS_HEADER = (
    "상가업소번호,상호명,지점명,상권업종소분류코드,상권업종소분류명,시도명,시군구명,법정동명,지번주소,"
    "도로명주소,층정보,경도,위도"
)


def semas_csv(rows: list[str]) -> str:
    return "\n".join([SEMAS_HEADER, *rows]) + "\n"


SEOUL_ROWS = [
    "S1,짠이네국수,홍대점,I20105,국수/칼국수,서울특별시,마포구,서교동,서울특별시 마포구 서교동 1,"
    "서울특별시 마포구 어울마당로 10,1,126.9245,37.5572",
    "S2,커피한잔,,I21201,카페,서울특별시,마포구,서교동,서울특별시 마포구 서교동 2,"
    "서울특별시 마포구 어울마당로 12,1,126.9250,37.5575",
    "S3,한빛구내식당,,I20101,백반/한정식,서울특별시,마포구,서교동,,서울특별시 마포구 어울마당로 14,,126.9251,37.5576",
    "S4,동네편의점,,G20405,편의점,서울특별시,마포구,서교동,,서울특별시 마포구 어울마당로 16,,126.9252,37.5577",
    "S5,좌표없는집,,I20101,백반/한정식,서울특별시,마포구,서교동,,서울특별시 마포구 어울마당로 18,,,",
    "S6,삼삼뚝배기,,I20101,백반/한정식,서울특별시,종로구,동숭동,,서울특별시 종로구 동숭길 51,,127.0030,37.5825",
]
JEJU_ROWS = [
    "J1,바당횟집,,I20111,횟집,제주특별자치도,제주시,연동,,제주특별자치도 제주시 신대로 1,,126.4920,33.4870",
]


def prior() -> PricePrior:
    return PricePrior.from_data(load_json("price_prior.json"), load_json("regions_kr.json"))


def mapper() -> semas_store.SemasMapper:
    categories = {"I20105": "food.noodle", "I21201": "cafe", "I20101": "food.korean", "I20111": "food.korean"}
    return semas_store.SemasMapper.from_data(categories, load_json("bulk_rules.json"), prior())


# --- CSV streaming ---------------------------------------------------------------------------


def test_sniff_encoding_handles_cut_multibyte_tail() -> None:
    utf8 = "상호명,주소\n".encode()
    assert sniff_encoding(utf8[:-2] if utf8[-1] < 0x80 else utf8) == "utf-8-sig"
    assert sniff_encoding("가나다".encode()[:-1]) == "utf-8-sig"  # cut in the middle of a character
    assert sniff_encoding("상호명,주소\n".encode("cp949")) == "cp949"


def test_iter_csv_reads_cp949_file_and_utf8_zip_members(tmp_path: Path) -> None:
    cp949 = tmp_path / "goodprice.csv"
    cp949.write_bytes("업소명,주소\n삼삼 뚝배기,서울특별시 종로구 동숭길 51\n".encode("cp949"))
    assert list(iter_csv(cp949)) == [{"업소명": "삼삼 뚝배기", "주소": "서울특별시 종로구 동숭길 51"}]

    archive = tmp_path / "store.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("readme.txt", "ignore me")
        zf.writestr("상가_제주_202606.csv", BOM + semas_csv(JEJU_ROWS))
        zf.writestr("상가_서울_202606.csv", BOM + semas_csv(SEOUL_ROWS))
    members = semas_store.ordered_members(archive)
    assert [m.split("_")[1] for m in members] == ["서울", "제주"]  # owner's priority order
    assert semas_store.ordered_members(archive, only=["제주"]) == ["상가_제주_202606.csv"]
    rows = list(iter_csv(archive, members[1]))
    assert rows[0]["상가업소번호"] == "J1" and rows[0]["위도"] == "33.4870"


# --- semas mapping / exclusions / price prior ------------------------------------------------


def test_semas_mapper_maps_excludes_and_estimates_price() -> None:
    rows = list(iter_csv_text(semas_csv(SEOUL_ROWS + JEJU_ROWS)))
    m = mapper()
    assert [m.skip_reason(r) for r in rows] == [
        None,
        None,
        "excluded_name",  # 구내식당
        "unmapped_category",  # 편의점
        "bad_coord",
        None,
        None,
    ]
    noodle = m.to_place(rows[0])
    assert noodle is not None
    assert noodle.name == "짠이네국수 홍대점" and noodle.category_code == "food.noodle"
    assert noodle.external_id == "S1" and noodle.provider == "semas"
    assert noodle.price_per_person == 9000 and noodle.price_is_estimated is True  # 서울 factor 1.0
    assert (noodle.sido, noodle.sigungu) == ("서울특별시", "마포구")
    assert m.to_place(rows[2]) is None


def test_code_to_category_reads_provider_mapping() -> None:
    mapping = semas_store.code_to_category(
        [("cafe", {"semas": ["I21201"], "kakao": ["CE7"]}), ("food", {}), ("bar.pub", {"semas": ["I21103"]})]
    )
    assert mapping == {"I21201": "cafe", "I21103": "bar.pub"}


def test_seed_categories_cover_every_priced_semas_code() -> None:
    """The reviewed price table and the category mapping are both DATA and must stay in sync."""
    import json

    seed = json.loads((API_ROOT / "data" / "seed" / "categories.json").read_text(encoding="utf-8"))
    mapped = {c for cat in seed["categories"] for c in cat["provider_mapping"].get("semas", [])}
    priced = set(load_json("price_prior.json")["by_semas_code"])
    assert mapped == priced
    assert not mapped & {"I20701", "I21101", "I21102", "R10406"}  # 구내식당 · 유흥주점 · PC방


def test_price_prior_factor_fallback_and_rounding() -> None:
    p = prior()
    assert p.estimate("cafe", "서울특별시", "I21201") == 6000
    assert p.estimate("cafe", "부산광역시", "I21201") == 5400  # × 0.9
    assert p.estimate("food.korean", "전라남도") == p.estimate("food.korean", "전남광주통합특별시")
    assert p.estimate("food.unknown_child", "서울특별시") == p.estimate(
        "food", "서울특별시"
    )  # parent fallback
    assert p.estimate("attraction.park", "서울특별시") is None
    value = p.estimate("food.bbq", "경기도")
    assert value is not None and value % 100 == 0


def test_price_prior_name_rules_beat_the_category_average() -> None:
    """A coin karaoke is not a karaoke room and a 2,000-won-americano chain is not an average café:
    two people were quoted 16,000원 for a coin karaoke before these rules existed."""
    p = prior()
    seoul = "서울특별시"
    room = p.estimate("activity.karaoke", seoul, "R10407", "황제노래연습장")
    coin = p.estimate("activity.karaoke", seoul, "R10407", "세븐스타 코인노래연습장 홍대점")
    assert room is not None and coin is not None and coin <= 3500 < room

    average_cafe = p.estimate("cafe", seoul, "I21201", "동네커피집")
    assert p.estimate("cafe", seoul, "I21201", "메가엠지씨커피 신촌점") < 3500 < average_cafe  # type: ignore[operator]
    assert p.estimate("cafe", seoul, "I21201", "스타벅스 강남R") > average_cafe  # type: ignore[operator]
    assert p.estimate("cafe", "부산광역시", "I21201", "컴포즈커피 서면점") == 2500  # 2,800 × 0.9, rounded

    # a rule only applies inside its categories: a bar called "메가…" keeps the bar price
    assert p.estimate("bar.pub", seoul, None, "메가엠포차") == p.estimate("bar.pub", seoul)
    # no name → exactly the old behaviour
    assert p.estimate("cafe", seoul, "I21201") == 6000


# --- regions ---------------------------------------------------------------------------------


def test_romanized_slugs_match_the_seed_convention() -> None:
    assert romanize("마포") == "mapo" and romanize("성동") == "seongdong"
    assert sigungu_slug("seoul", "마포구") == "seoul-mapo"
    assert sigungu_slug("busan", "부산진구") == "busan-busanjin"
    assert sigungu_slug("gyeonggi", "수원시 팔달구") == "gyeonggi-suwon-paldal"
    assert sigungu_slug("seoul", "중구") == "seoul-jung"


def test_dense_center_prefers_the_town_over_the_mean() -> None:
    cloud = PointCloud()
    for i in range(50):  # downtown
        cloud.add(37.5000 + i * 0.00002, 127.0000 + i * 0.00002)
    for i in range(10):  # a far-away village
        cloud.add(37.8000 + i * 0.0001, 127.4000)
    lat, lng = dense_center(cloud)
    assert abs(lat - 37.5005) < 0.002 and abs(lng - 127.0005) < 0.002
    assert percentile_radius(cloud, (lat, lng), 0.9, 1500, 6000) == 6000  # clamped
    assert percentile_radius(cloud, (lat, lng), 0.5, 1500, 6000) == 1500


def test_build_region_rows_levels_parents_and_hotspots() -> None:
    stats = RegionStats()
    for _ in range(5):
        stats.add("서울특별시", "마포구", 37.5572, 126.9245)
        stats.add("세종특별자치시", "세종특별자치시", 36.4800, 127.2890)
    rows = build_region_rows(load_json("regions_kr.json"), stats)
    by_slug = {r["slug"]: r for r in rows}
    assert by_slug["seoul"]["level"] == 1 and by_slug["seoul"]["area_code"] == "1"
    assert by_slug["seoul-mapo"]["parent"] == "seoul" and by_slug["seoul-mapo"]["level"] == 2
    assert by_slug["seoul-hongdae"]["parent"] == "seoul-mapo" and by_slug["seoul-hongdae"]["level"] == 3
    assert by_slug["sejong-sejong"]["parent"] == "sejong"  # 세종: the 시군구 carries the 시도 name
    assert "busan-seomyeon" not in by_slug  # its 시군구 is not loaded → no orphan hotspot
    assert [r["level"] for r in rows] == sorted(r["level"] for r in rows)  # parents first
    assert all(r["status"] == "active" for r in rows)


def test_hotspot_slug_colliding_with_its_sigungu_is_rejected() -> None:
    # "해운대구" romanises to busan-haeundae: a hotspot with that slug would overwrite the 시군구 row on
    # upsert and become its own parent (this happened — 해운대구·영등포구·부평구 vanished from the tree).
    spec = dict(load_json("regions_kr.json"))
    spec["hotspots"] = [
        {
            "slug": "busan-haeundae",
            "name": "해운대",
            "sido": "부산광역시",
            "sigungu": "해운대구",
            "center": [35.163, 129.16],
            "radius_m": 1200,
        }
    ]
    stats = RegionStats()
    stats.add("부산광역시", "해운대구", 35.163, 129.16)
    with pytest.raises(ValueError, match="busan-haeundae"):
        build_region_rows(spec, stats)


def test_shipped_hotspots_never_collide_and_always_hang_under_a_sigungu() -> None:
    """Runs the real data file with every 시군구 its hotspots name — the guard above must stay silent."""
    spec = load_json("regions_kr.json")
    stats = RegionStats()
    for h in spec["hotspots"]:
        stats.add(h["sido"], h["sigungu"], h["center"][0], h["center"][1])
    rows = build_region_rows(spec, stats)
    by_slug = {r["slug"]: r for r in rows}
    assert len(by_slug) == len(rows)  # slugs are unique across all three levels
    for h in spec["hotspots"]:
        row = by_slug[h["slug"]]
        assert row["level"] == 3
        assert by_slug[row["parent"]]["level"] == 2, h["slug"]


def test_admin_from_address() -> None:
    assert runner.admin_from_address("서울특별시 마포구 양화로 160") == ("서울특별시", "마포구")
    assert runner.admin_from_address("경기도 수원시 팔달구 정조로 800") == ("경기도", "수원시 팔달구")
    assert runner.admin_from_address("강원특별자치도 강릉시 창해로 17") == ("강원특별자치도", "강릉시")
    assert runner.admin_from_address(None) == (None, None)
    assert runner.admin_from_address("제주") == (None, None)


# --- 착한가격업소 -------------------------------------------------------------------------------


def test_address_key_normalises_both_files() -> None:
    aliases = {"전라남도": "전남광주통합특별시", "서울특별시": "서울특별시"}
    a = goodprice.address_key("서울특별시 종로구 동숭길 51 (동숭동)", aliases)
    b = goodprice.address_key("서울특별시 종로구 동숭길 51", aliases)
    assert a == b == ("서울특별시", "종로구", "동숭길", "51")
    assert goodprice.address_key("경기도 수원시 팔달구 정조로 800-1, 2층") == (
        "경기도",
        "팔달구",
        "정조로",
        "800-1",
    )
    assert goodprice.address_key("전라남도 여수시 중앙로 5", aliases) == (
        "전남광주통합특별시",
        "여수시",
        "중앙로",
        "5",
    )
    assert goodprice.address_key("서울특별시 종로구 동숭동 1-2") is None  # 지번 address


def test_goodprice_rows_menus_and_categories() -> None:
    text = (
        "시도,시군,업종,업소명,연락처,주소,메뉴1,가격1,메뉴2,가격2,메뉴3,가격3,메뉴4,가격4\n"
        '서울특별시,종로구,한식,삼삼 뚝배기,02-765-4683,서울특별시 종로구 동숭길 51 (동숭동),된장뚝배기,7500,김치찌개,"7,500원",,,,\n'
        "서울특별시,종로구,기타요식업,약속커피숍,,서울특별시 종로구 종로 302 (창신동),맥심커피,2000,녹차,2000,,,,\n"
        "서울특별시,종로구,미용업,영미용실,,서울특별시 종로구 지봉로 62,커트,8000,,,,,,\n"
        "서울특별시,종로구,한식,가격없는집,,서울특별시 종로구 지봉로 63,백반,,,,,,,\n"
    )
    report = BulkReport()
    rules = load_json("bulk_rules.json")["goodprice"]
    rows = goodprice.parse_rows(iter_csv_text(text), rules, report)
    assert [r.name for r in rows] == ["삼삼 뚝배기", "약속커피숍"]
    assert [m.price for m in rows[0].menus] == [7500, 7500] and rows[0].menus[0].is_signature
    assert report.skip_reasons == {"not_food": 1, "no_menu": 1}
    by_kind = {"한식": "food.korean"}
    assert goodprice.category_for(rows[0], by_kind, rules) == "food.korean"
    assert goodprice.category_for(rows[1], by_kind, rules) == "cafe"  # 기타요식업 + 커피 menu

    coords = goodprice.building_coords(iter_csv_text(semas_csv(SEOUL_ROWS)), {r.key for r in rows})
    assert coords == {("서울특별시", "종로구", "동숭길", "51"): (37.5825, 127.003)}

    existing = GridIndex()
    existing.add(dedupe.ExistingPlace(77, "삼삼뚝배기", 37.5825, 127.0030))
    places = list(goodprice.to_places(rows, coords, existing, by_kind, rules, report))
    assert len(places) == 1 and report.skip_reasons["address_not_in_store_file"] == 1
    merged = places[0]
    assert merged.merge_into_place_id == 77  # same building + same name → enrich, do not duplicate
    assert merged.price_per_person == 7500 and merged.price_is_estimated is False
    assert (merged.lat, merged.lng) == (37.5825, 127.003)


def test_grid_index_finds_only_nearby_similar_names() -> None:
    index = GridIndex()
    index.add(dedupe.ExistingPlace(1, "서울숲 공원", 37.5443, 127.0374))
    index.add(dedupe.ExistingPlace(2, "서울숲 공원", 37.6000, 127.1000))  # same name, far away
    match = index.find_match("서울숲공원", 37.54432, 127.03741)
    assert match is not None and match.place_id == 1
    assert index.find_match("전혀 다른 곳", 37.5443, 127.0374) is None
    assert len(index.near(37.5443, 127.0374)) == 1 and len(index) == 2


# --- 표준데이터 --------------------------------------------------------------------------------


def test_std_parks_filter_by_kind_and_area() -> None:
    spec = load_json("bulk_rules.json")["std"]["parks"]
    text = (
        "관리번호,공원명,공원구분,소재지도로명주소,소재지지번주소,위도,경도,공원면적,전화번호\n"
        "P-1,큰근린공원,근린공원,,서울특별시 마포구 1,37.55,126.92,50000,02-1\n"
        "P-2,작은근린공원,근린공원,,서울특별시 마포구 2,37.55,126.92,900,\n"
        "P-3,꼬마어린이공원,어린이공원,,서울특별시 마포구 3,37.55,126.92,50000,\n"
        "P-4,좌표없는공원,근린공원,,서울특별시 마포구 4,,,50000,\n"
    )
    report = BulkReport()
    places = list(std_datasets.iter_places(iter_csv_text(text), spec, report))
    assert [p.external_id for p in places] == ["P-1"]
    park = places[0]
    assert park.category_code == "attraction.park" and park.is_free and park.price_per_person is None
    assert report.skip_reasons == {"excluded_kind": 2, "no_coord": 1}


def test_std_museum_price_hours_and_gallery_category() -> None:
    spec = load_json("bulk_rules.json")["std"]["museums"]
    header = (
        "시설명,소재지도로명주소,소재지지번주소,위도,경도,운영기관전화번호,평일관람시작시각,평일관람종료시각,"
        "공휴일관람시작시각,공휴일관람종료시각,휴관정보,어른관람료,박물관미술관소개\n"
    )
    text = header + (
        "한빛미술관,서울특별시 종로구 삼청로 1,,37.58,126.98,02-1,10:00,18:00,10:00,17:00,매주 월요일,5000,현대미술\n"
        "무료박물관,서울특별시 종로구 삼청로 2,,37.58,126.98,,00:00,00:00,00:00,00:00,연중무휴,0,\n"
    )
    gallery, free = list(std_datasets.iter_places(iter_csv_text(text), spec, BulkReport()))
    assert gallery.category_code == "culture.gallery" and free.category_code == "culture.museum"
    assert gallery.price_per_person == 5000 and not gallery.price_is_estimated and not gallery.is_free
    assert free.is_free and free.price_per_person is None
    assert free.hours == []  # 00:00–00:00 = not stated, never "open 24 h"
    assert len(gallery.hours) == 7 and gallery.hours[0].is_closed  # Monday
    assert (gallery.hours[1].open_time, gallery.hours[1].close_time) == ("10:00", "18:00")
    assert gallery.hours[6].close_time == "17:00"
    assert gallery.external_id != free.external_id and len(gallery.external_id) == 20


def test_std_festival_to_event() -> None:
    spec = load_json("bulk_rules.json")["std"]["festivals"]
    text = (
        "축제명,개최장소,축제시작일자,축제종료일자,축제내용,소재지도로명주소,소재지지번주소,위도,경도,홈페이지주소\n"
        "파주포크페스티벌,임진각평화누리공원,2026-09-05,2026-09-06,포크 공연,경기도 파주시 임진각로 148-40,,37.892,126.744,https://x.kr\n"
        "좌표없는축제,어딘가,2026-10-01,2026-10-02,,,,,,\n"
        "날짜이상축제,어딘가,2026-10-05,2026-10-01,,,,37.5,127.0,\n"
    )
    report = BulkReport()
    events = list(std_datasets.iter_events(iter_csv_text(text), spec, report))
    assert len(events) == 1 and report.skip_reasons == {"no_coord": 1, "bad_dates": 1}
    e = events[0]
    assert (e.starts_on, e.ends_on) == (date(2026, 9, 5), date(2026, 9, 6))
    assert e.category_code == "culture.festival" and "임진각평화누리공원" in (e.address or "")


def test_std_markets_keep_permanent_markets_only() -> None:
    spec = load_json("bulk_rules.json")["std"]["markets"]
    text = (
        "시장명,시장유형,소재지도로명주소,소재지지번주소,위도,경도,전화번호\n"
        "망원시장,상설장,서울특별시 마포구 포은로 1,,37.556,126.905,\n"
        "어느오일장,5일장,강원특별자치도 정선군 1,,37.38,128.66,\n"
    )
    places = list(std_datasets.iter_places(iter_csv_text(text), spec, BulkReport()))
    assert [p.name for p in places] == ["망원시장"] and places[0].category_code == "attraction.market"


# --- download helper (pure parts) -------------------------------------------------------------


def test_download_helpers_parse_page_and_write_csv(tmp_path: Path) -> None:
    html = """<a onclick="fileDetailObj.fn_fileDataDown('15083033', 'uddi:abc-123', '','1', '1')">"""
    assert parse_detail_pk(html, "15083033") == ("uddi:abc-123", "1")
    assert parse_detail_pk(html, "999") is None
    out = tmp_path / "std.csv"
    n = rows_to_csv(
        out, ["공원명", "위도"], ["PARK_NM", "LATITUDE"], [[{"PARK_NM": "a,b", "LATITUDE": None}]]
    )
    assert n == 1 and list(iter_csv(out)) == [{"공원명": "a,b", "위도": ""}]
    sources = load_sources()
    assert {"semas", "goodprice", "parks", "museums", "tourist", "festivals", "markets"} <= set(sources)
    steps = manual_steps(sources["semas"], tmp_path / "semas_store.zip")
    assert "data.go.kr/data/15083033/fileData.do" in steps and "--path" in steps


# --- end to end on a throw-away SQLite file ----------------------------------------------------


@pytest.mark.asyncio
async def test_bulk_load_is_idempotent_and_measured_prices_survive(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        app_env="test",
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'bulk.db').as_posix()}",
    )
    db = Database(settings)
    quiet = lambda _msg: None  # noqa: E731
    try:
        await db.create_all()
        async with db.sessionmaker() as session:
            await load_config(session, API_ROOT / "data" / "seed")
            await session.commit()

        store = tmp_path / "store.zip"
        with zipfile.ZipFile(store, "w") as zf:
            zf.writestr("상가_서울_202606.csv", BOM + semas_csv(SEOUL_ROWS))
        first = await runner.load_semas(db, store, log=quiet)
        assert (first.read, first.created, first.skipped) == (6, 3, 3)
        again = await runner.load_semas(db, store, log=quiet)
        assert (again.created, again.updated, again.unchanged) == (0, 0, 3)

        good = tmp_path / "goodprice.csv"
        good.write_bytes(
            (
                "시도,시군,업종,업소명,연락처,주소,메뉴1,가격1,메뉴2,가격2,메뉴3,가격3,메뉴4,가격4\n"
                "서울특별시,종로구,한식,삼삼 뚝배기,02-765-4683,서울특별시 종로구 동숭길 51 (동숭동),"
                "된장뚝배기,7500,김치찌개,7500,,,,\n"
                "서울특별시,마포구,한식,새로생긴밥집,,서울특별시 마포구 어울마당로 10,백반,8000,,,,,,\n"
            ).encode("cp949")
        )
        gp = await runner.load_goodprice(db, good, store, log=quiet)
        assert (gp.merged, gp.created) == (1, 1)
        assert (await runner.load_goodprice(db, good, store, log=quiet)).unchanged == 2

        # the store file changes (renamed shop): the category prior must not overwrite the menu price
        renamed = [r.replace("S6,삼삼뚝배기", "S6,삼삼뚝배기 본점") for r in SEOUL_ROWS]
        with zipfile.ZipFile(store, "w") as zf:
            zf.writestr("상가_서울_202606.csv", BOM + semas_csv(renamed[:1] + renamed[5:]))
        third = await runner.load_semas(db, store, close_unseen=True, log=quiet)
        assert (third.updated, third.unchanged, third.closed) == (1, 1, 1)  # S2 vanished → closed

        festivals = tmp_path / "festivals.csv"
        festivals.write_text(
            "축제명,개최장소,축제시작일자,축제종료일자,축제내용,소재지도로명주소,소재지지번주소,위도,경도,홈페이지주소\n"
            "홍대거리축제,걷고싶은거리,2026-09-20,2026-09-22,,서울특별시 마포구 어울마당로 1,,37.5570,126.9240,\n",
            encoding="utf-8-sig",
        )
        for _ in range(2):  # twice → still one row
            await runner.load_std(db, "festivals", festivals, log=quiet)

        async with db.sessionmaker() as session:
            shop = await session.scalar(select(Place).where(Place.name == "삼삼뚝배기 본점"))
            assert shop is not None
            assert shop.price_per_person == 7500 and shop.price_is_estimated is False
            assert shop.phone == "02-765-4683" and shop.status == "approved"
            menus = (await session.scalars(select(MenuItem).where(MenuItem.place_id == shop.id))).all()
            assert sorted(m.name for m in menus) == ["김치찌개", "된장뚝배기"]
            sources = (
                await session.scalars(select(PlaceSource).where(PlaceSource.place_id == shop.id))
            ).all()
            assert {s.provider for s in sources} == {"semas", "goodprice"}

            noodle = await session.scalar(select(Place).where(Place.name == "짠이네국수 홍대점"))
            assert noodle is not None and noodle.price_is_estimated and noodle.price_per_person == 9000
            hongdae = await session.scalar(select(Region).where(Region.slug == "seoul-hongdae"))
            assert hongdae is not None and noodle.region_id == hongdae.id  # most specific region
            assert hongdae.area_code == "1:13"  # hand-entered seed value survives regeneration

            cafe = await session.scalar(select(Place).where(Place.name == "커피한잔"))
            assert cafe is not None and cafe.status == "closed"
            stats = await session.get(PlaceStats, noodle.id)
            assert stats is not None and stats.rating_avg is None and stats.rating_count == 0
            assert await session.scalar(select(func.count(Place.id))) == 4
            assert await session.scalar(select(func.count(OpeningHour.id))) == 0
            assert await session.scalar(select(func.count(Event.id))) == 1

        summary = await runner.stats(db)
        assert summary["price"] == {"estimated": 1, "measured": 2, "free": 0}
        assert summary["places_by_sido"] == {"서울특별시": 3}

        # The store is back in the official open-stores file (or an exclusion rule was relaxed):
        # "closed" means out of business, so an unchanged row must come back as approved.
        with zipfile.ZipFile(store, "w") as zf:
            zf.writestr("상가_서울_202606.csv", BOM + semas_csv(renamed))
        fourth = await runner.load_semas(db, store, close_unseen=True, log=quiet)
        assert (fourth.reopened, fourth.closed) == (1, 0)
        async with db.sessionmaker() as session:
            cafe = await session.scalar(select(Place).where(Place.name == "커피한잔"))
            assert cafe is not None and cafe.status == "approved"
    finally:
        await db.dispose()


def iter_csv_text(text: str) -> list[dict[str, str]]:
    import csv

    return [dict(row) for row in csv.DictReader(io.StringIO(text))]


def test_display_name_ignores_company_suffix_in_branch_column() -> None:
    from app.infra.ingestion.bulk.semas_store import display_name

    assert display_name("커피빈홍대역8번출구점", "코리아") == "커피빈홍대역8번출구점"
    assert display_name("스타벅스", "홍대역점") == "스타벅스 홍대역점"
    assert display_name("스타벅스 홍대역점", "홍대역점") == "스타벅스 홍대역점"


def test_a_name_says_what_the_code_does_not() -> None:
    # 2026-09-25: 사진촬영업(M11301) was dropped whole — 셀프 사진관 never reached a date; 타로 카페 were plain cafés
    photo = [
        "P1,인생네컷 홍대점,,M11301,사진촬영업,서울특별시,마포구,서교동,,서울특별시 마포구 와우산로 1,,126.9230,37.5560",
        "P2,한빛웨딩스튜디오,,M11301,사진촬영업,서울특별시,마포구,서교동,,서울특별시 마포구 와우산로 2,,126.9231,37.5561",
        "P3,미래안사주까페,,I21201,카페,서울특별시,마포구,서교동,,서울특별시 마포구 와우산로 3,,126.9232,37.5562",
        "P4,짠이커피,,I21201,카페,서울특별시,마포구,서교동,,서울특별시 마포구 와우산로 4,,126.9233,37.5563",
    ]
    rows = list(iter_csv_text(semas_csv(photo)))
    m = mapper()
    assert [m.category_for(r) for r in rows] == ["activity.photo", None, "activity.fortune", "cafe"]
    assert m.skip_reason(rows[1]) == "unmapped_category"  # a wedding studio is not a date stop
    tarot = m.to_place(rows[2])
    assert tarot is not None and tarot.price_per_person is not None and tarot.price_per_person >= 10000
