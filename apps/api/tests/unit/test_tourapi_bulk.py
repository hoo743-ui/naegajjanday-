from __future__ import annotations

from app.infra.ingestion.bulk import tourapi_bulk as T
from app.infra.ingestion.bulk.common import BulkReport, load_json
from app.infra.ingestion.bulk.runner import _event_key

RULES = load_json("bulk_rules.json")["tourapi"]


def item(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "contentid": "126508",
        "title": "경의선숲길",
        "lclsSystm3": "VE030100",
        "mapx": "126.9245",
        "mapy": "37.5572",
        "addr1": "서울특별시 마포구 연남동",
        "addr2": "",
        "tel": "",
        "firstimage": "http://tong.visitkorea.or.kr/cms/resource/1/park.jpg",
        "firstimage2": "",
        "cpyrhtDivCd": "Type3",
    }
    return {**base, **over}


def test_most_specific_classification_wins() -> None:
    assert T.category_for(item(lclsSystm3="VE030100"), RULES) == "attraction.park"
    assert T.category_for(item(lclsSystm3="VE010200"), RULES) == "nightview.observatory"  # 8자 미지정 → 4자
    assert T.category_for(item(lclsSystm3="VE070600"), RULES) == "culture.gallery"
    assert T.category_for(item(lclsSystm3="FD020200"), RULES) == "food.japanese"
    assert T.category_for(item(lclsSystm3="HS030100"), RULES) == "attraction.landmark"  # 2자 대분류


def test_places_nobody_visits_on_a_day_course_are_skipped() -> None:
    for code in ("AC050100", "LS010400", "LS020500", "SH040300", "VE090300"):  # 캠핑·골프·낚시·상점·도서관
        assert T.category_for(item(lclsSystm3=code), RULES) is None
    place, reason = T.to_place(item(lclsSystm3="AC050100"), RULES, None, {})
    assert place is None and reason == "unmapped_category"
    assert T.to_place(item(title="더바디성형외과의원", lclsSystm3="EX050800"), RULES, None, {})[0] is None


def test_place_carries_its_real_photo_over_https() -> None:
    place, _ = T.to_place(item(), RULES, None, {"서울특별시": "서울"})
    assert place is not None and place.provider == "tourapi" and place.external_id == "126508"
    assert place.thumbnail_url == "https://tong.visitkorea.or.kr/cms/resource/1/park.jpg"
    assert (
        place.is_free
        and place.price_per_person is None
        and place.sido == "서울"
        and place.sigungu == "마포구"
    )
    # 사진이 바뀌면 다시 써야 한다 → 해시에 들어간다
    other, _ = T.to_place(item(firstimage="http://tong.visitkorea.or.kr/x.jpg"), RULES, None, {})
    assert other is not None and other.content_hash != place.content_hash


def test_bad_rows_are_counted_not_raised() -> None:
    report = BulkReport()
    rows = [item(), item(contentid="2", mapx="0", mapy="0"), item(contentid="3", title="")]
    out = list(T.iter_places(iter(rows), RULES, None, {}, report))
    assert len(out) == 1 and report.read == 3 and report.skipped == 2
    assert dict(report.skip_reasons) == {"bad_coord": 1, "no_name": 1}


def test_festival_dates_photo_and_kind() -> None:
    fest = item(
        title="강릉커피축제", lclsSystm3="EV010100", eventstartdate="20261001", eventenddate="20261004"
    )
    event, _ = T.to_event(fest, RULES)
    assert event is not None and event.category_code == "culture.festival"
    assert (event.starts_on.isoformat(), event.ends_on.isoformat()) == ("2026-10-01", "2026-10-04")
    assert event.images == ["https://tong.visitkorea.or.kr/cms/resource/1/park.jpg"]
    expo, _ = T.to_event({**fest, "lclsSystm3": "EV030100"}, RULES)
    assert expo is not None and expo.category_code == "culture.exhibition"
    assert T.to_event({**fest, "eventstartdate": ""}, RULES) == (None, "no_title_or_date")


def test_same_festival_from_two_sources_has_one_key() -> None:
    assert _event_key("제17회 광주국제아트페어") == _event_key("2026 광주국제아트페어")
    assert _event_key("강릉커피축제") != _event_key("강릉단오제")
