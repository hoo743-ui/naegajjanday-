"""docs/44: 더 알아보기 링크는 검색 목록이 아니라 그 장소의 페이지로 — 이름과 위치가 모두 맞을 때만."""

from __future__ import annotations

import pytest

from app.services.link_service import area_of, build_links, clean_url, pick_kakao


@pytest.mark.parametrize(
    ("raw", "url"),
    [
        (
            '<a href="http://www.gyeongbokgung.go.kr" target="_blank" title="새창">www.gyeongbokgung.go.kr</a>',
            "http://www.gyeongbokgung.go.kr",
        ),
        ("https://www.pajucf.or.kr/main/main.php", "https://www.pajucf.or.kr/main/main.php"),
        ("www.gcfest.or.kr", "http://www.gcfest.or.kr"),
        ("홈페이지 : &lt;a href=&quot;https://seoul.go.kr&quot;&gt;", "https://seoul.go.kr"),
        ("javascript:alert(1)", None),
        ("", None),
        (None, None),
        ("없음", None),
        ("https://korean.visitkorea.or.kr/", None),  # 포털 첫 화면
        (
            "https://korean.visitkorea.or.kr/detail/ms_detail.do?cotid=x",
            "https://korean.visitkorea.or.kr/detail/ms_detail.do?cotid=x",
        ),
    ],
)
def test_clean_url(raw: str | None, url: str | None) -> None:
    assert clean_url(raw) == url


DOCS = [
    {
        "id": "1",
        "place_name": "서울숲",
        "x": "127.0374",
        "y": "37.5444",
        "place_url": "http://place.map.kakao.com/1",
    },
    {
        "id": "2",
        "place_name": "서울숲 카페",
        "x": "127.0400",
        "y": "37.5450",
        "place_url": "http://place.map.kakao.com/2",
    },
]


def test_pick_kakao_needs_name_and_position() -> None:
    assert pick_kakao(DOCS, "서울숲", 37.5443, 127.0375)["id"] == "1"
    # 같은 이름이라도 1km 넘게 떨어져 있으면 그 장소가 아니다
    assert pick_kakao(DOCS, "서울숲", 37.5543, 127.0375) is None
    # 가까워도 이름이 다르면 아니다
    assert pick_kakao(DOCS, "뚝섬한강공원", 37.5443, 127.0375) is None


def test_matched_place_links_straight_to_its_page() -> None:
    links = build_links(
        name="서울숲",
        lat=37.5443,
        lng=127.0375,
        address="서울특별시 성동구 뚝섬로 273",
        official="https://parks.seoul.go.kr",
        kakao=DOCS[0],
        festival=False,
    )
    by = {link.kind: link for link in links}
    assert [link.kind for link in links] == ["official", "place_page", "blog", "route"]
    assert by["place_page"].url == "https://place.map.kakao.com/1" and by["place_page"].exact
    assert by["route"].url == "https://map.kakao.com/link/to/1"
    assert "where=blog" in by["blog"].url and "%EC%84%B1%EB%8F%99%EA%B5%AC" in by["blog"].url  # 성동구


def test_unmatched_place_falls_back_to_search_marked_inexact() -> None:
    links = build_links(
        name="어느 전시", lat=37.5, lng=127.0, address=None, official=None, kakao=None, festival=True
    )
    assert [link.kind for link in links] == ["place_page", "blog", "route"]
    assert not links[0].exact and links[0].label == "카카오맵에서 찾기"


def test_area_of() -> None:
    assert area_of("서울특별시 성동구 성수동2가 1") == "성동구"
    assert area_of(None) == ""
