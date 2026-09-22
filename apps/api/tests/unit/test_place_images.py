"""Place image pipeline (docs/29 §16-27): verified, one owner per photo, never twice in a course."""

from __future__ import annotations

from datetime import UTC, datetime

from app.domain import media as M
from app.services.image_service import address_match, candidates_for

LARGE = "https://tong.visitkorea.or.kr/cms/resource/42/4111342_image2_1.jpg"
SMALL = "https://tong.visitkorea.or.kr/cms/resource/42/4111342_image3_1.jpg"
PHOTO_DIR = "https://tong.visitkorea.or.kr/cms/resource_photo/98/4111342_image2_1.jpg"
NOW = datetime(2026, 9, 22, tzinfo=UTC)


def ev(name: float = 1.0, dist: float | None = 0.0, addr: bool = False, **kw: bool) -> M.Evidence:
    return M.Evidence(name, dist, addr, **kw)


class TestSamePhoto:
    def test_two_sizes_are_one_photo(self) -> None:
        assert M.image_key(LARGE) == M.image_key(SMALL)

    def test_another_folder_is_another_photo(self) -> None:
        assert M.image_key(PHOTO_DIR) != M.image_key(LARGE)

    def test_other_hosts_ignore_the_query(self) -> None:
        assert M.image_key("https://ex.org/a.jpg?w=200") == M.image_key("https://EX.org/a.jpg")


class TestIdentity:
    def test_the_name_in_brackets_counts(self) -> None:
        assert M.name_similarity("한려해상국립공원 (오동도)", "오동도") == 1.0
        assert (
            M.name_similarity("서울 구 벨기에영사관 (현 서울시립 남서울미술관)", "서울시립 남서울미술관")
            == 1.0
        )
        assert M.name_similarity("[K드라마 촬영지] 공근혜갤러리", "공근혜갤러리") == 1.0

    def test_a_name_ending_in_jeom_is_not_emptied(self) -> None:
        assert M.name_similarity("대동백화점", "대동백화점") == 1.0

    def test_different_shops_are_different(self) -> None:
        assert M.name_similarity("스타벅스", "이디야커피") < 0.5

    def test_verification(self) -> None:
        assert M.verify(ev(1.0, 5.0)) == M.VERIFIED
        assert M.verify(ev(0.8, 200.0)) == M.LIKELY
        assert M.verify(ev(0.6, 5.0, addr=True)) == M.LIKELY  # same door, shortened name
        assert M.verify(ev(0.3, 5.0)) == M.REJECTED  # another shop's record
        assert M.verify(ev(1.0, 2500.0)) == M.REJECTED  # same name, another town
        assert M.verify(ev(1.0, 250.0, generic_name=True)) == M.UNVERIFIED  # "카페" 250 m away
        assert M.verify(ev(0.0, None, owner_upload=True)) == M.VERIFIED

    def test_relevance_is_lower_for_a_duplicate_and_bounded(self) -> None:
        good = M.relevance(ev(1.0, 0.0), "tourapi", modified=NOW, now=NOW)
        assert 0 < M.relevance(ev(1.0, 0.0), "tourapi", modified=NOW, now=NOW, duplicate=True) < good <= 1


class TestJudge:
    def test_a_shared_photo_stays_with_the_place_it_describes(self) -> None:
        right = M.Candidate(1, LARGE, "tourapi", ev(1.0, 0.0))
        wrong = M.Candidate(2, SMALL, "tourapi", ev(0.9, 40.0))
        M.judge([right, wrong], NOW)
        assert right.status == M.VERIFIED
        assert wrong.status == M.REJECTED and "place 1" in (wrong.note or "")

    def test_projection_shows_each_photo_once_and_uploads_first(self) -> None:
        tour = M.Candidate(1, LARGE, "tourapi", ev(1.0, 0.0))
        upload = M.Candidate(1, "https://cdn.example/own.jpg", "upload", ev(owner_upload=True))
        bad = M.Candidate(1, PHOTO_DIR, "tourapi", ev(0.2, 0.0))
        M.judge([tour, upload, bad], NOW)
        cover, urls = M.projection([tour, upload, bad])
        assert cover == upload.url
        assert urls == [upload.url, LARGE]

    def test_nothing_showable_means_no_photo(self) -> None:
        bad = M.Candidate(1, LARGE, "tourapi", ev(0.2, 0.0))
        M.judge([bad], NOW)
        assert M.projection([bad]) == (None, [])


def test_one_course_never_shows_a_photo_twice() -> None:
    assert M.distinct_photos([LARGE, None, SMALL, PHOTO_DIR]) == [LARGE, None, None, PHOTO_DIR]


class TestSourceRecords:
    def test_address_match(self) -> None:
        assert address_match("서울특별시 관악구 남부순환로 2076", "서울특별시 관악구 남부순환로 2076")
        assert address_match("충청남도 태안군 남면 연꽃길 70", "충청남도 태안군 남면 연꽃길 70-1")
        assert not address_match("충청남도 태안군 남면 연꽃길 70", "충청남도 태안군 남면 연꽃길 12")
        assert not address_match(None, "어딘가 1")

    def test_one_candidate_per_photo_with_its_evidence(self) -> None:
        record = {
            "title": "청산수목원",
            "addr1": "충청남도 태안군 남면 연꽃길 70",
            "mapx": "126.2968709883",
            "mapy": "36.6886163907",
            "firstimage": LARGE.replace("https", "http"),
            "firstimage2": SMALL,
            "modifiedtime": "20260920013003",
        }
        found = candidates_for(
            7,
            "청산수목원",
            "충청남도 태안군 남면 연꽃길 70",
            36.6886163907,
            126.2968709883,
            [],
            "129601",
            record,
        )
        assert len(found) == 1
        c = found[0]
        assert c.url == LARGE and c.sizes == [SMALL]
        assert c.evidence.name_similarity == 1.0 and c.evidence.address_match
        assert c.source_place_id == "129601"
        M.judge(found, NOW)
        assert c.status == M.VERIFIED and M.showable(c)
