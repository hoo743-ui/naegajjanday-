"""docs/34: where a campus is placed, and that its id never changes once given."""

from __future__ import annotations

from app.infra.ingestion.bulk.universities import School, assign_ids, pick_kakao_match


def school(name: str, road: str, eng: str = "Sample University") -> School:
    return School(name, eng, "본교", "대학", "대학교", "경기도", road, "", "", "")


def doc(
    name: str, address: str, category: str = "교육,학문 > 학교 > 대학교", y: str = "37.45", x: str = "127.13"
) -> dict:
    return {
        "place_name": name,
        "road_address_name": address,
        "address_name": "",
        "category_name": category,
        "y": y,
        "x": x,
    }


def test_kakao_answer_is_kept_only_when_it_is_that_school() -> None:
    gachon = school("가천대학교", "경기도 성남시 수정구 성남대로 1342")
    docs = [
        doc("스타벅스 가천대학교점", "경기 성남시 수정구 성남대로 1342", category="음식점 > 카페"),  # a shop
        doc(
            "가천대학교 글로벌캠퍼스 비전타워", "경기 성남시 수정구 성남대로 1342", y="1", x="1"
        ),  # a building
        doc("가천대학교 글로벌캠퍼스", "경기 성남시 수정구 성남대로 1342", y="37.4504", x="127.1299"),
        doc("가천대학교 메디컬캠퍼스", "인천 연수구 함박뫼로 191", y="9", x="9"),  # another city
    ]
    assert pick_kakao_match(gachon, docs) == (37.4504, 127.1299)
    assert pick_kakao_match(gachon, [docs[0], docs[3]]) is None  # nothing that is this campus → unplaced


def test_ids_already_given_are_kept() -> None:
    a = school("가나대학교", "경기도 성남시 수정구 A로 1")
    b = school("가나대학교", "경기도 안성시 B로 2")  # same English name, another campus
    fresh = assign_ids([(a, None), (b, None)])
    assert fresh == {0: "sample-university", 1: "sample-university-2"}
    # a new school placed in front of them (now found by Kakao) must not shift their ids
    c = school("다라대학교", "서울특별시 종로구 C로 3")
    known = {(a.name, a.road_address): "sample-university", (b.name, b.road_address): "sample-university-2"}
    ids = assign_ids([(c, None), (b, None), (a, None)], known)
    assert (
        ids[1] == "sample-university-2" and ids[2] == "sample-university" and ids[0] == "sample-university-3"
    )
