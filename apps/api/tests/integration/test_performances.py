"""GET /v1/performances with the upstream faked (httpx.MockTransport) — and the no-key path."""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest
from fastapi import FastAPI

from app.api.v1.performances import performance_source
from app.infra.ingestion.providers.kopis import KopisClient, KopisRules

LAT, LNG = 37.5572, 126.9245  # centre of a seeded test region
ATTRIBUTION = "출처: (재)예술경영지원센터 공연예술통합전산망(www.kopis.or.kr)"


def _list_row(pid: str, title: str, venue: str) -> str:
    return (
        f"<db><mt20id>{pid}</mt20id><prfnm>{title}</prfnm><prfpdfrom>2026.09.01</prfpdfrom>"
        f"<prfpdto>2026.10.31</prfpdto><fcltynm>{venue}</fcltynm>"
        f"<poster>http://www.kopis.or.kr/upload/{pid}.gif</poster><genrenm>연극</genrenm></db>"
    )


def _detail(pid: str, title: str, venue: str, venue_id: str, guidance: str, runtime: str) -> str:
    return (
        f"<dbs><db><mt20id>{pid}</mt20id><mt10id>{venue_id}</mt10id><prfnm>{title}</prfnm>"
        f"<prfpdfrom>2026.09.01</prfpdfrom><prfpdto>2026.10.31</prfpdto><fcltynm>{venue}</fcltynm>"
        f"<prfruntime>{runtime}</prfruntime><pcseguidance>전석 30,000원</pcseguidance>"
        f"<dtguidance>{guidance}</dtguidance></db></dbs>"
    )


def _venue(venue_id: str, name: str, lat: float, lng: float) -> str:
    return (
        f"<dbs><db><fcltynm>{name}</fcltynm><mt10id>{venue_id}</mt10id>"
        f"<adres>테스트시 테스트구 테스트로 1</adres><la>{lat}</la><lo>{lng}</lo></db></dbs>"
    )


PERFORMANCES = {
    # near, Saturday 15:00 + 19:00, 90 min
    "PF1": ("가까운 연극", "가까운홀", "FC1", "화요일 ~ 금요일(20:00), 토요일(15:00,19:00)", "1시간 30분"),
    # near, but dark on Saturdays
    "PF2": ("평일만 하는 연극", "가까운홀", "FC1", "화요일 ~ 금요일(20:00)", "1시간 30분"),
    # Saturday 15:00 but ~9 km away
    "PF3": ("먼 곳의 뮤지컬", "먼홀", "FC2", "토요일(15:00)", "2시간"),
    # near, Saturday 15:00, but four hours long → does not end in time
    "PF4": ("너무 긴 공연", "가까운홀", "FC1", "토요일(15:00)", "4시간"),
}
VENUES = {"FC1": ("가까운홀", LAT + 0.003, LNG), "FC2": ("먼홀", LAT + 0.08, LNG)}


class Upstream:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path.endswith("/pblprfr"):
            rows = "".join(_list_row(pid, p[0], p[1]) for pid, p in PERFORMANCES.items())
            return httpx.Response(200, text=f"<dbs>{rows}</dbs>")
        ident = path.rsplit("/", 1)[-1]
        if "/pblprfr/" in path and ident in PERFORMANCES:
            title, venue, venue_id, guidance, runtime = PERFORMANCES[ident]
            return httpx.Response(200, text=_detail(ident, title, venue, venue_id, guidance, runtime))
        if "/prfplc/" in path and ident in VENUES:
            return httpx.Response(200, text=_venue(ident, *VENUES[ident]))
        return httpx.Response(404)


@pytest.fixture
def upstream(app: FastAPI) -> Iterator[Upstream]:
    fake = Upstream()
    rules = KopisRules(
        attribution=ATTRIBUTION,
        detail_url_template="https://www.kopis.or.kr/por/db/pblprfr/pblprfrView.do?mt20Id={id}",
        area_codes_by_sido_slug={"seoul": ("11",)},
    )
    client = KopisClient("test-key", rules, transport=httpx.MockTransport(fake))
    app.dependency_overrides[performance_source] = lambda: client
    yield fake
    app.dependency_overrides.pop(performance_source, None)


SATURDAY_2PM = {"lat": LAT, "lng": LNG, "radius_m": 2000, "start_at": "2026-09-26T14:00:00+09:00"}


async def test_without_a_key_the_feature_is_off(client: httpx.AsyncClient) -> None:
    resp = await client.get("/v1/performances", params={**SATURDAY_2PM, "duration_min": 240})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["items"] == [] and body["available"] is False
    assert "KOPIS" in body["reason"] and body["attribution"] == ATTRIBUTION
    features = (await client.get("/v1/meta/features")).json()
    assert features["performances"] is False and "chat" in features


async def test_only_nearby_performances_with_a_show_in_the_window(
    client: httpx.AsyncClient, upstream: Upstream
) -> None:
    resp = await client.get("/v1/performances", params={**SATURDAY_2PM, "duration_min": 240})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["available"] is True and body["partial"] is False and body["attribution"] == ATTRIBUTION
    assert [i["id"] for i in body["items"]] == ["PF1"]
    item = body["items"][0]
    assert item["title"] == "가까운 연극" and item["show_times"] == ["15:00"]  # 19:00 is after the window
    assert item["runtime_min"] == 90 and item["price_text"] == "전석 30,000원"
    assert item["venue"]["name"] == "가까운홀" and 300 < item["venue"]["distance_m"] < 400
    assert item["poster_url"] == "https://www.kopis.or.kr/upload/PF1.gif"
    assert item["detail_url"].endswith("mt20Id=PF1")
    listed = [r for r in upstream.requests if r.url.path.endswith("/pblprfr")]
    assert len(listed) == 1 and listed[0].url.params["stdate"] == "20260926"
    assert listed[0].url.params["signgucode"] == "11"  # nearest region → its 시도 → area code


async def test_second_view_is_served_from_the_cache(client: httpx.AsyncClient, upstream: Upstream) -> None:
    params = {**SATURDAY_2PM, "duration_min": 240}
    first = (await client.get("/v1/performances", params=params)).json()
    calls = len(upstream.requests)
    assert calls == 1 + 4 + 2  # list + 4 details + 2 venues
    again = (await client.get("/v1/performances", params={**params, "duration_min": 480})).json()
    assert len(upstream.requests) == calls
    assert first["items"][0]["show_times"] == ["15:00"]
    assert {i["id"]: i["show_times"] for i in again["items"]} == {"PF1": ["15:00", "19:00"], "PF4": ["15:00"]}


async def test_no_show_in_the_window_gives_a_reason(client: httpx.AsyncClient, upstream: Upstream) -> None:
    monday = {**SATURDAY_2PM, "start_at": "2026-09-21T14:00:00+09:00", "duration_min": 240}
    body = (await client.get("/v1/performances", params=monday)).json()
    assert body["items"] == [] and body["available"] is True and body["reason"]


async def test_call_budget_makes_the_answer_partial(client: httpx.AsyncClient, app: FastAPI) -> None:
    fake = Upstream()
    rules = KopisRules(attribution=ATTRIBUTION, max_upstream_calls_per_request=2, concurrency=1)
    source = KopisClient("test-key", rules, transport=httpx.MockTransport(fake))
    app.dependency_overrides[performance_source] = lambda: source
    try:
        params = {**SATURDAY_2PM, "duration_min": 240}
        body = (await client.get("/v1/performances", params=params)).json()
        assert body["partial"] is True
        assert len(fake.requests) == 1 + 2  # the list + exactly the budgeted calls
        for _ in range(4):  # the cache fills up view by view until the answer is complete
            body = (await client.get("/v1/performances", params=params)).json()
        assert body["partial"] is False and [i["id"] for i in body["items"]] == ["PF1"]
    finally:
        app.dependency_overrides.pop(performance_source, None)


async def test_bad_input_is_a_422(client: httpx.AsyncClient) -> None:
    resp = await client.get("/v1/performances", params={"lat": 1, "lng": 2})
    assert resp.status_code == 422
