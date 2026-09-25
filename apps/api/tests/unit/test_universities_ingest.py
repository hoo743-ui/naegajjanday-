"""docs/34: where a campus is placed, and that its id never changes once given."""

from __future__ import annotations

from app.infra.ingestion.bulk.universities import (
    School,
    assign_ids,
    campus_label,
    drop_close_campuses,
    other_campuses,
    pick_kakao_match,
)


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


def grad(name: str, road: str) -> dict[str, str]:
    return {
        "대학구분명": "대학원",
        "학교명": name,
        "시도명": "",
        "소재지도로명주소": road,
        "소재지지번주소": "",
    }


def test_a_graduate_school_elsewhere_is_another_campus() -> None:
    gachon = school("가천대학교", "경기도 성남시 수정구 성남대로 1342")
    rows = [
        grad("가천대학교 교육대학원", "경기도 성남시 수정구 성남대로 1342"),  # the same campus
        grad("가천대학교 보건대학원", "인천광역시 연수구 함박뫼로 191"),
        grad("가천대학교 간호대학원", "인천광역시 연수구 함박뫼로 191 (연수동)"),  # the same one again
        grad("나다대학교 대학원", "서울특별시 종로구 A로 1"),  # no undergraduate row → not ours to add
    ]
    found = other_campuses(rows, [gachon], [])
    assert [(s.name, s.road_address) for s in found] == [("가천대학교", "인천광역시 연수구 함박뫼로 191")]
    skipped = other_campuses(rows, [gachon], [], {"가천대학교": ["함박뫼로 191"]})
    assert skipped == []


def test_campus_label_matches_the_whole_number() -> None:
    labels = {"서울대학교": {"관악로 1": "관악캠퍼스", "대학로 103": "연건캠퍼스"}}
    assert campus_label(labels, "서울대학교", "서울특별시 관악구 관악로 1") == "관악캠퍼스"
    assert campus_label(labels, "서울대학교", "서울특별시 관악구 관악로 12") == ""
    labelled = school("서울대학교", "서울특별시 종로구 대학로 103")
    labelled.label = "연건캠퍼스"
    assert labelled.display_name == "서울대학교 연건캠퍼스"


def test_a_derived_campus_next_to_another_is_dropped() -> None:
    main = school("서울대학교", "서울특별시 종로구 대학로 103")
    near = School(
        "서울대학교", "", "캠퍼스", "대학", "대학교", "", "서울특별시 종로구 대학로 101", "", "", ""
    )
    far = School(
        "서울대학교", "", "캠퍼스", "대학", "대학교", "", "강원특별자치도 평창군 평창대로 1447-1", "", "", ""
    )
    kept, dropped = drop_close_campuses(
        [(near, (37.5801, 126.9995, "x")), (main, (37.5796, 126.9990, "x")), (far, (37.54, 128.44, "x"))]
    )
    assert [s.road_address for s, _ in kept] == [main.road_address, far.road_address]
    assert len(dropped) == 1
