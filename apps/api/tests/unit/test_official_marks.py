"""백년가게 · 모범음식점 · 인허가 표식: parsing, the address join and the tag rules (no DB)."""

from __future__ import annotations

from datetime import date

from app.infra.ingestion.bulk import official_marks as om
from app.infra.ingestion.bulk.common import BulkReport, load_json
from app.infra.ingestion.bulk.download import load_sources

ALIASES = {
    "서울": "서울특별시",
    "서울특별시": "서울특별시",
    "강원": "강원특별자치도",
    "강원특별자치도": "강원특별자치도",
}
MODEL = {
    "provider": "model_restaurant",
    "name_column": "업소명",
    "address_columns": ["도로명주소"],
    "id_column": "관리번호",
    "status_column": "영업상태코드",
    "open_values": ["01"],
    "revoked_column": "지정취소일자",
    "redesignated_column": "재지정일자",
    "keep_columns": ["지정일자", "주된음식종류"],
    "tag": "모범음식점",
}
LICENCE = {
    "provider": "lic_restaurant",
    "name_column": "사업장명",
    "address_columns": ["도로명주소"],
    "id_column": "관리번호",
    "status_column": "영업상태코드",
    "open_values": ["01"],
    "licensed_column": "인허가일자",
    "age_tags": [{"min_years": 30, "tag": "30년 넘은 집"}],
}


def _model_row(**over: str) -> dict[str, str]:
    row = {
        "관리번호": "3000000-101-1999-10390",
        "업소명": "더레스토랑",
        "도로명주소": "서울특별시 종로구 삼청로 54, 지하1층 (소격동)",
        "영업상태코드": "01",
        "지정일자": "2007-11-20",
        "지정취소일자": "",
        "재지정일자": "",
        "주된음식종류": "스테이크",
    }
    return {**row, **over}


def test_split_road_name_is_joined() -> None:
    assert om.mark_address_key("강원 속초시 중앙로 129번길 35-17(금호동)", ALIASES) == (
        "강원특별자치도",
        "속초시",
        "중앙로129번길",
        "35-17",
    )
    assert om.mark_address_key("서울 종로구 삼청로 54", ALIASES) == ("서울특별시", "종로구", "삼청로", "54")


def test_parse_date_accepts_the_formats_in_the_files() -> None:
    assert om.parse_date("1993-11-12") == date(1993, 11, 12)
    assert om.parse_date("19931112") == date(1993, 11, 12)
    assert om.parse_date("") is None
    assert om.parse_date("1993-13-40") is None


def test_revoked_designation_is_dropped_unless_redesignated_later() -> None:
    report = BulkReport()
    rows = [
        _model_row(),
        _model_row(관리번호="b", 지정취소일자="2024-02-15", 재지정일자="2023-11-29"),  # revoked after
        _model_row(관리번호="c", 지정취소일자="2020-01-01", 재지정일자="2025-12-10"),  # designated again
        _model_row(관리번호="d", 영업상태코드="02"),  # out of business
    ]
    kept = [r.external_id for r in om.iter_rows(rows, MODEL, report, ALIASES)]
    assert kept == ["3000000-101-1999-10390", "c"]
    assert report.skip_reasons["not_current"] == 2


def test_match_needs_the_same_building_and_a_similar_name() -> None:
    index = om.PlaceAddressIndex()
    index.add(1, "더 레스토랑", "서울특별시 종로구 삼청로 54", ALIASES)
    index.add(2, "삼청동수제비", "서울특별시 종로구 삼청로 54", ALIASES)
    index.add(3, "더레스토랑", "서울특별시 종로구 삼청로 99", ALIASES)  # same name, other building
    report = BulkReport()
    rows = list(
        om.iter_rows([_model_row(), _model_row(관리번호="x", 업소명="전혀다른집")], MODEL, report, ALIASES)
    )
    matches = om.match_rows(rows, index, 0.75, report)
    assert [(m.place_id, m.row.external_id) for m in matches] == [(1, "3000000-101-1999-10390")]
    assert report.skip_reasons["no_matching_place"] == 1
    assert matches[0].row.raw["주된음식종류"] == "스테이크"


def test_one_mark_per_place_keeps_the_closer_name() -> None:
    index = om.PlaceAddressIndex()
    index.add(1, "장미횟집", "서울특별시 종로구 삼청로 54", ALIASES)
    report = BulkReport()
    rows = list(
        om.iter_rows(
            [_model_row(관리번호="a", 업소명="장미회집"), _model_row(관리번호="b", 업소명="장미횟집")],
            MODEL,
            report,
            ALIASES,
        )
    )
    matches = om.match_rows(rows, index, 0.75, report)
    assert [m.row.external_id for m in matches] == ["b"]


def test_age_tag_only_from_the_licence_date() -> None:
    today = date(2026, 9, 21)
    assert om.years_open(date(1996, 9, 21), today) == 30
    assert om.years_open(date(1996, 9, 22), today) == 29
    assert om.years_open(date(2030, 1, 1), today) is None
    row = om.MarkRow("a", "귀빈", ("서울특별시", "종로구", "수표로26길", "12"), {}, date(1993, 11, 12))
    young = om.MarkRow("b", "새집", ("서울특별시", "종로구", "수표로26길", "12"), {}, date(2020, 1, 1))
    assert om.tags_for(om.MarkMatch(row, 1, 1.0), LICENCE, today) == {"30년 넘은 집": 1.0}
    assert om.tags_for(om.MarkMatch(young, 2, 1.0), LICENCE, today) == {}
    assert om.tags_for(om.MarkMatch(young, 2, 1.0), MODEL, today) == {"모범음식점": 1.0}


def test_inherited_licence_of_a_branch_or_chain_gets_no_age_tag() -> None:
    today = date(2026, 9, 21)
    old = om.MarkRow(
        "a", "빽돈 중구 을지로", ("서울특별시", "중구", "을지로14길", "22"), {}, date(1990, 1, 1)
    )
    assert om.tags_for(om.MarkMatch(old, 1, 0.9, "빽돈 을지로점"), LICENCE, today) == {}
    assert om.tags_for(om.MarkMatch(old, 1, 0.9, "역전할머니맥주"), LICENCE, today, ("역전할머니",)) == {}
    assert om.tags_for(om.MarkMatch(old, 1, 0.9, "하동관 본점"), LICENCE, today) == {"30년 넘은 집": 1.0}
    assert om.tags_for(om.MarkMatch(old, 1, 0.9, "이문설농탕"), LICENCE, today) == {"30년 넘은 집": 1.0}


def test_every_mark_in_the_rules_has_a_source_and_a_short_provider() -> None:
    marks = {k: v for k, v in load_json("bulk_rules.json")["marks"].items() if not k.startswith("_")}
    sources = load_sources()
    for kind, spec in marks.items():
        assert kind in sources, kind
        assert len(spec["provider"]) <= 32
        assert spec.get("tag") or spec.get("age_tags") or spec.get("hide"), f"{kind} does nothing"
    assert sources["lic_restaurants"].page_url == "https://file.localdata.go.kr/file/general_restaurants/info"
