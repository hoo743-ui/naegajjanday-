"""KOPIS provider: parsing of sample XML (hand-written to the documented shape, fictional content),
the no-key path and the TTL cache. No network: httpx.MockTransport."""

from __future__ import annotations

from datetime import date

import httpx

from app.infra.ingestion.providers.kopis import (
    KopisClient,
    KopisRules,
    TTLCache,
    load_rules,
    parse_detail,
    parse_list,
    parse_venue,
)

LIST_XML = """<?xml version="1.0" encoding="UTF-8"?>
<dbs>
  <db>
    <mt20id>PF000001</mt20id>
    <prfnm>테스트 연극 하나</prfnm>
    <prfpdfrom>2026.09.01</prfpdfrom>
    <prfpdto>2026.10.31</prfpdto>
    <fcltynm>테스트아트홀 1관</fcltynm>
    <poster>http://www.kopis.or.kr/upload/pfmPoster/PF_PF000001.gif</poster>
    <area>테스트특별시</area>
    <genrenm>연극</genrenm>
    <openrun>N</openrun>
    <prfstate>공연중</prfstate>
  </db>
  <db>
    <mt20id>PF000002</mt20id>
    <prfnm>테스트 뮤지컬 둘</prfnm>
    <prfpdfrom>2026.09.20</prfpdfrom>
    <prfpdto>2026.09.27</prfpdto>
    <fcltynm>먼곳극장</fcltynm>
    <poster></poster>
    <genrenm>뮤지컬</genrenm>
    <prfstate>공연중</prfstate>
  </db>
  <db>
    <prfnm>아이디가 없는 행</prfnm>
  </db>
</dbs>"""

DETAIL_XML = """<?xml version="1.0" encoding="UTF-8"?>
<dbs>
  <db>
    <mt20id>PF000001</mt20id>
    <mt10id>FC000001</mt10id>
    <prfnm>테스트 연극 하나</prfnm>
    <prfpdfrom>2026.09.01</prfpdfrom>
    <prfpdto>2026.10.31</prfpdto>
    <fcltynm>테스트아트홀 1관</fcltynm>
    <prfruntime>1시간 30분</prfruntime>
    <pcseguidance>전석 30,000원</pcseguidance>
    <poster>http://www.kopis.or.kr/upload/pfmPoster/PF_PF000001.gif</poster>
    <genrenm>연극</genrenm>
    <prfstate>공연중</prfstate>
    <styurls><styurl>http://www.kopis.or.kr/upload/pfmIntroImage/a.jpg</styurl></styurls>
    <dtguidance>화요일 ~ 금요일(20:00), 토요일(15:00,19:00), 일요일(14:00)</dtguidance>
  </db>
</dbs>"""

VENUE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<dbs>
  <db>
    <fcltynm>테스트아트홀</fcltynm>
    <mt10id>FC000001</mt10id>
    <mt13cnt>2</mt13cnt>
    <seatscale>300</seatscale>
    <telno>02-000-0000</telno>
    <adres>테스트특별시 테스트구 테스트로 1</adres>
    <la>37.5572</la>
    <lo>126.9245</lo>
  </db>
</dbs>"""

ERROR_XML = """<?xml version="1.0" encoding="UTF-8"?>
<dbs><db><returncode>02</returncode><errmsg>SERVICE KEY IS NOT REGISTERED</errmsg></db></dbs>"""


class TestParsing:
    def test_list(self) -> None:
        rows = parse_list(LIST_XML)
        assert [r.id for r in rows] == ["PF000001", "PF000002"]  # the row without an id is dropped
        first = rows[0]
        assert (first.title, first.venue_name, first.genre) == (
            "테스트 연극 하나",
            "테스트아트홀 1관",
            "연극",
        )
        assert (first.date_from, first.date_to) == (date(2026, 9, 1), date(2026, 10, 31))
        assert first.poster_url is not None and first.poster_url.startswith("https://")
        assert rows[1].poster_url is None

    def test_detail(self) -> None:
        d = parse_detail(DETAIL_XML)
        assert d is not None
        assert (d.id, d.venue_id, d.runtime_text, d.price_text) == (
            "PF000001",
            "FC000001",
            "1시간 30분",
            "전석 30,000원",
        )
        assert d.showtimes_text is not None and d.showtimes_text.startswith("화요일 ~ 금요일(20:00)")

    def test_venue(self) -> None:
        v = parse_venue(VENUE_XML)
        assert v is not None
        assert (v.id, v.name, v.lat, v.lng) == ("FC000001", "테스트아트홀", 37.5572, 126.9245)
        assert v.address == "테스트특별시 테스트구 테스트로 1"

    def test_error_answer_and_broken_xml_are_empty(self) -> None:
        assert parse_list(ERROR_XML) == [] and parse_detail(ERROR_XML) is None
        assert parse_list("<dbs><db>") == [] and parse_venue(b"not xml at all") is None
        assert parse_list("<dbs/>") == []

    def test_venue_with_bad_coordinates(self) -> None:
        v = parse_venue("<dbs><db><mt10id>FC9</mt10id><fcltynm>x</fcltynm><la>abc</la><lo></lo></db></dbs>")
        assert v is not None and v.lat is None and v.lng is None


def _transport(calls: list[httpx.Request]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        path = request.url.path
        if path.endswith("/pblprfr"):
            return httpx.Response(200, text=LIST_XML)
        if "/pblprfr/" in path:
            return httpx.Response(200, text=DETAIL_XML)
        if "/prfplc/" in path:
            return httpx.Response(200, text=VENUE_XML)
        return httpx.Response(404)

    return httpx.MockTransport(handler)


class TestClient:
    async def test_without_a_key_nothing_is_requested(self) -> None:
        calls: list[httpx.Request] = []
        for key in ("", "   ", None):
            client = KopisClient(key, KopisRules(), transport=_transport(calls))
            assert client.available is False
            assert await client.list_performances(date(2026, 9, 26), date(2026, 9, 26)) == []
            assert await client.detail("PF000001") is None
            assert await client.venue("FC000001") is None
        assert calls == [] and client.upstream_calls == 0

    async def test_list_detail_venue_and_request_shape(self) -> None:
        calls: list[httpx.Request] = []
        client = KopisClient("k-test", KopisRules(), transport=_transport(calls))
        rows = await client.list_performances(date(2026, 9, 26), date(2026, 9, 26), area_code="11")
        assert len(rows) == 2
        params = dict(calls[0].url.params)
        assert params == {
            "service": "k-test",
            "stdate": "20260926",
            "eddate": "20260926",
            "cpage": "1",
            "rows": "100",
            "signgucode": "11",
        }
        detail = await client.detail("PF000001")
        assert detail is not None and detail.venue_id == "FC000001"
        assert client.known_venue_id("테스트아트홀 1관") == "FC000001"
        venue = await client.venue("FC000001")
        assert venue is not None and venue.lat == 37.5572

    async def test_responses_are_cached_until_the_ttl_runs_out(self) -> None:
        calls: list[httpx.Request] = []
        now = [1000.0]
        rules = KopisRules(ttl_detail_s=60)
        client = KopisClient("k-test", rules, transport=_transport(calls), clock=lambda: now[0])
        assert client.is_cached("detail", "PF000001") is False
        for _ in range(3):
            assert await client.detail("PF000001") is not None
        assert len(calls) == 1 and client.is_cached("detail", "PF000001")
        now[0] += 61
        assert await client.detail("PF000001") is not None
        assert len(calls) == 2 == client.upstream_calls

    async def test_pagination_stops_at_a_short_page_and_at_the_cap(self) -> None:
        calls: list[httpx.Request] = []
        short = KopisClient("k", KopisRules(rows=100), transport=_transport(calls))
        await short.list_performances(date(2026, 9, 26), date(2026, 9, 26))
        assert len(calls) == 1  # 2 rows < 100 → no second page
        calls.clear()
        full = KopisClient("k", KopisRules(rows=2, max_list_pages=3), transport=_transport(calls))
        rows = await full.list_performances(date(2026, 9, 26), date(2026, 9, 26))
        assert len(calls) == 3 and len(rows) == 6

    async def test_upstream_failure_is_empty_and_not_cached(self) -> None:
        hits = [0]

        def handler(_: httpx.Request) -> httpx.Response:
            hits[0] += 1
            return httpx.Response(500)

        client = KopisClient("k", KopisRules(), transport=httpx.MockTransport(handler))
        assert await client.detail("PF000001") is None
        assert await client.detail("PF000001") is None
        assert hits[0] == 2 and not client.is_cached("detail", "PF000001")

    async def test_odd_ids_never_reach_the_url(self) -> None:
        calls: list[httpx.Request] = []
        client = KopisClient("k", KopisRules(), transport=_transport(calls))
        assert await client.detail("../prfplc/FC1") is None and await client.venue("a b") is None
        assert calls == []


def test_ttl_cache_evicts_expired_entries() -> None:
    now = [0.0]
    cache = TTLCache(clock=lambda: now[0], max_items=2)
    cache.put("a", 1, 10)
    cache.put("b", 2, 100)
    now[0] = 50
    cache.put("c", 3, 100)  # full → expired "a" is dropped
    assert "a" not in cache and cache.get("b") == 2 and cache.get("c") == 3


def test_rules_file_is_valid() -> None:
    rules = load_rules()
    assert rules.base_url.startswith("https://") and "kopis.or.kr" in rules.attribution
    assert rules.detail_url("PF1") and rules.detail_url("PF1").endswith("PF1")  # type: ignore[union-attr]
    assert all(codes for codes in rules.area_codes_by_sido_slug.values())
    assert rules.max_upstream_calls_per_request > 0
