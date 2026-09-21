from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import Any

import httpx
import pytest

from app.infra.analytics.base import AnalyticsEvent
from app.infra.analytics.ga4 import GA4Tracker
from app.infra.analytics.mixpanel import MixpanelTracker
from app.infra.analytics.posthog import PostHogTracker
from app.infra.ingestion.base import (
    NormalizedEvent,
    NormalizedPlace,
    ProviderNotConfiguredError,
    RawPlace,
    RegionRef,
)
from app.infra.ingestion.providers.data_go_kr import CITY_PARK_FIELD_MAP, DataGoKrProvider
from app.infra.ingestion.providers.google_places import GooglePlacesProvider, google_day_to_dow
from app.infra.ingestion.providers.kakao_local import KakaoLocalProvider
from app.infra.ingestion.providers.naver_search import NaverSearchProvider
from app.infra.ingestion.providers.tourapi import TourApiProvider, extract_items, parse_area_code
from app.infra.llm.anthropic_provider import AnthropicProvider, build_request_kwargs, to_anthropic_messages
from app.infra.llm.base import LLMMessage, LLMNotConfiguredError, LLMRequest, ToolCall, ToolResult, ToolSpec
from app.infra.llm.gemini_provider import sanitize_schema, to_gemini_contents
from app.infra.llm.openai_provider import build_payload as build_openai_payload

REGION = RegionRef(
    slug="test-region",
    name="테스트",
    center_lat=37.5572,
    center_lng=126.9245,
    radius_m=1200,
    area_code="1:13",
    search_keywords=("테스트 맛집",),
)


# ---------------------------------------------------------------- ingestion: normalize


def test_kakao_normalize() -> None:
    provider = KakaoLocalProvider("key")
    raw = RawPlace(
        provider="kakao_local",
        external_id="26338954",
        raw={
            "id": "26338954",
            "place_name": "샘플 국수집",
            "category_group_code": "FD6",
            "category_name": "음식점 > 한식 > 국수",
            "x": "126.9251",
            "y": "37.5568",
            "address_name": "서울 마포구 서교동 000-0",
            "road_address_name": "서울 마포구 샘플로 1",
            "phone": "02-000-0000",
        },
    )
    place = provider.normalize(raw)
    assert isinstance(place, NormalizedPlace)
    assert (place.lat, place.lng) == (37.5568, 126.9251)
    assert place.provider_categories == ["FD6", "음식점 > 한식 > 국수"]
    assert place.category_code is None
    assert place.rating_avg is None and place.price_per_person is None
    assert provider.normalize(RawPlace("kakao_local", "x", {"place_name": "좌표없음"})) is None


def test_naver_normalize_scales_coords_and_strips_bold() -> None:
    provider = NaverSearchProvider("id", "secret")
    raw = RawPlace(
        provider="naver_search",
        external_id="abc",
        raw={
            "title": "<b>샘플</b> 로스터리",
            "category": "카페,디저트>카페",
            "address": "서울특별시 마포구 서교동 000-0",
            "roadAddress": "서울특별시 마포구 샘플로 2",
            "telephone": "",
            "mapx": "1269245000",
            "mapy": "375572000",
        },
    )
    place = provider.normalize(raw)
    assert isinstance(place, NormalizedPlace)
    assert place.name == "샘플 로스터리"
    assert place.lng == pytest.approx(126.9245)
    assert place.lat == pytest.approx(37.5572)
    assert place.phone is None
    assert place.provider_categories == ["카페,디저트>카페"]


def test_google_normalize_maps_sunday_and_keeps_no_review_text() -> None:
    assert google_day_to_dow(0) == 6  # Sunday
    assert google_day_to_dow(1) == 0  # Monday
    provider = GooglePlacesProvider("key")
    raw = RawPlace(
        provider="google_places",
        external_id="ChIJsample",
        raw={
            "id": "ChIJsample",
            "displayName": {"text": "샘플 비스트로", "languageCode": "ko"},
            "formattedAddress": "대한민국 서울특별시 마포구 샘플로 3",
            "location": {"latitude": 37.556, "longitude": 126.923},
            "types": ["restaurant", "food", "point_of_interest"],
            "primaryType": "restaurant",
            "rating": 4.4,
            "userRatingCount": 321,
            "priceLevel": "PRICE_LEVEL_MODERATE",
            "reviews": [{"text": {"text": "must not be stored"}}],
            "regularOpeningHours": {
                "periods": [
                    {
                        "open": {"day": 0, "hour": 11, "minute": 0},
                        "close": {"day": 0, "hour": 21, "minute": 0},
                    },
                    {
                        "open": {"day": 1, "hour": 11, "minute": 30},
                        "close": {"day": 1, "hour": 15, "minute": 0},
                    },
                    {
                        "open": {"day": 1, "hour": 17, "minute": 0},
                        "close": {"day": 1, "hour": 22, "minute": 0},
                    },
                ]
            },
        },
    )
    place = provider.normalize(raw)
    assert isinstance(place, NormalizedPlace)
    assert place.rating_avg == 4.4 and place.rating_count == 321
    assert place.price_per_person is None
    assert place.provider_categories[0] == "restaurant"
    hours = {h.dow: h for h in place.opening_hours}
    assert hours[6].open_time == "11:00" and hours[6].close_time == "21:00"  # Google Sunday → dow 6
    assert (hours[0].open_time, hours[0].close_time) == ("11:30", "22:00")
    assert (hours[0].break_start, hours[0].break_end) == ("15:00", "17:00")
    assert hours[2].is_closed
    assert "must not be stored" not in repr(place)
    assert "places.reviews" not in provider._headers(paged=True)["X-Goog-FieldMask"]


def test_tourapi_normalize_place_and_festival() -> None:
    provider = TourApiProvider("key")
    item: dict[str, Any] = {
        "contentid": "126508",
        "contenttypeid": "12",
        "title": "경의선숲길",
        "addr1": "서울특별시 마포구",
        "addr2": "연남동",
        "mapx": "126.9237",
        "mapy": "37.5598",
        "firstimage": "http://tong.visitkorea.or.kr/sample.jpg",
        "cat1": "A02",
        "cat2": "A0202",
        "cat3": "A02020700",
        "tel": "",
    }
    place = provider.normalize(RawPlace("tourapi", "126508", item))
    assert isinstance(place, NormalizedPlace)
    assert place.address == "서울특별시 마포구 연남동"
    assert place.provider_categories == ["A02020700", "A0202", "A02", "contenttype:12"]
    assert place.thumbnail_url == "http://tong.visitkorea.or.kr/sample.jpg"

    festival = {**item, "contentid": "9001", "contenttypeid": "15", "title": "샘플 거리축제"}
    festival |= {"eventstartdate": "20260918", "eventenddate": "20260928"}
    event = provider.normalize(RawPlace("tourapi", "9001", festival, kind="event"))
    assert isinstance(event, NormalizedEvent)
    assert (event.starts_on, event.ends_on) == (date(2026, 9, 18), date(2026, 9, 28))


def test_tourapi_quirks() -> None:
    assert parse_area_code("1:13") == ("1", "13")
    assert parse_area_code("6") == ("6", None)
    assert parse_area_code(None) == (None, None)
    assert extract_items({"response": {"body": {"items": "", "totalCount": 0}}}) == ([], 0)
    single = {"response": {"body": {"items": {"item": {"contentid": "1"}}, "totalCount": 1}}}
    assert extract_items(single) == ([{"contentid": "1"}], 1)


def test_data_go_kr_normalize_with_field_map() -> None:
    provider = DataGoKrProvider(
        "key", "http://example.invalid/api", CITY_PARK_FIELD_MAP, is_free=True, category_hint="park"
    )
    row = {
        "manageNo": "11440-00001",
        "parkNm": "샘플근린공원",
        "latitude": "37.5580",
        "longitude": "126.9250",
    }
    place = provider.normalize(RawPlace("data_go_kr", "11440-00001", row))
    assert isinstance(place, NormalizedPlace)
    assert place.is_free and place.provider_categories == ["park"]
    with pytest.raises(ValueError):
        DataGoKrProvider("key", "http://example.invalid/api", {"name": "parkNm"})


def test_missing_keys_raise() -> None:
    with pytest.raises(ProviderNotConfiguredError) as exc:
        KakaoLocalProvider(None)
    assert exc.value.env_var == "KAKAO_REST_API_KEY"
    with pytest.raises(ProviderNotConfiguredError):
        NaverSearchProvider("id", None)
    with pytest.raises(ProviderNotConfiguredError):
        GooglePlacesProvider("")
    with pytest.raises(ProviderNotConfiguredError):
        TourApiProvider(None)


# ---------------------------------------------------------------- ingestion: fetch (mock transport)


async def test_kakao_fetch_paginates_until_is_end(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.infra.ingestion.providers.kakao_local.PAGE_DELAY_S", 0)
    calls: list[tuple[str, dict[str, str]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        calls.append((request.url.path, params))
        assert request.headers["Authorization"] == "KakaoAK test-key"
        if request.url.path.endswith("keyword.json"):
            page = int(params["page"])
            docs = [{"id": f"k{page}", "place_name": f"장소{page}", "x": "126.92", "y": "37.55"}]
            return httpx.Response(200, json={"documents": docs, "meta": {"is_end": page >= 3}})
        dup = [{"id": "k1", "place_name": "장소1", "x": "126.92", "y": "37.55"}]  # duplicate is skipped
        return httpx.Response(200, json={"documents": dup, "meta": {"is_end": True}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = KakaoLocalProvider("test-key", client=client)
        raws = [raw async for raw in provider.fetch(REGION)]

    assert [r.external_id for r in raws] == ["k1", "k2", "k3"]
    keyword_calls = [p for path, p in calls if path.endswith("keyword.json")]
    assert [p["page"] for p in keyword_calls] == ["1", "2", "3"]
    assert keyword_calls[0]["radius"] == "1200" and keyword_calls[0]["size"] == "15"
    category_codes = [p["category_group_code"] for path, p in calls if path.endswith("category.json")]
    assert category_codes == ["FD6", "CE7", "AT4", "CT1"]
    assert all(r.content_hash for r in raws)


async def test_kakao_fetch_resumes_from_cursor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.infra.ingestion.providers.kakao_local.PAGE_DELAY_S", 0)
    pages: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("keyword.json"):
            pages.append(request.url.params["page"])
        return httpx.Response(200, json={"documents": [], "meta": {"is_end": True}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = KakaoLocalProvider("test-key", client=client)
        _ = [raw async for raw in provider.fetch(REGION, cursor={"query_index": 0, "page": 7})]
    assert pages == ["7"]


# ---------------------------------------------------------------- analytics payloads


async def test_analytics_payload_shapes() -> None:
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json={"status": 1})

    event = AnalyticsEvent(
        name="course_generated",
        distinct_id="u_123",
        properties={"region": "test-region", "budget_total": 40000, "saved": True},
        timestamp=datetime(2026, 9, 20, 9, 0, tzinfo=UTC),
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await GA4Tracker("G-TEST", "secret", client=client).track(event)
        await PostHogTracker("phc_test", "https://eu.i.posthog.com/", client=client).track(event)
        await MixpanelTracker("mp_token", client=client).track(event)

    ga4, posthog, mixpanel = sent
    assert ga4.url.params["measurement_id"] == "G-TEST" and ga4.url.params["api_secret"] == "secret"
    ga4_body = json.loads(ga4.content)
    assert ga4_body["client_id"] == "u_123"
    assert ga4_body["events"][0]["name"] == "course_generated"
    assert ga4_body["events"][0]["params"]["budget_total"] == 40000
    assert ga4_body["events"][0]["params"]["saved"] == 1

    assert str(posthog.url) == "https://eu.i.posthog.com/capture/"
    ph_body = json.loads(posthog.content)
    assert ph_body["api_key"] == "phc_test" and ph_body["distinct_id"] == "u_123"
    assert ph_body["event"] == "course_generated" and ph_body["timestamp"].startswith("2026-09-20T09:00:00")

    mp_body = json.loads(mixpanel.content)
    assert isinstance(mp_body, list)
    props = mp_body[0]["properties"]
    assert props["token"] == "mp_token" and props["distinct_id"] == "u_123"
    assert props["time"] == int(event.timestamp.timestamp()) and props["$insert_id"]


async def test_analytics_swallows_transport_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await PostHogTracker("phc_test", client=client).track(AnalyticsEvent("e", "anon"))


# ---------------------------------------------------------------- LLM request building (no network)

TOOL = ToolSpec(
    name="generate_course",
    description="코스를 생성한다",
    input_schema={
        "type": "object",
        "properties": {"region": {"type": "string"}},
        "required": ["region"],
        "additionalProperties": False,
    },
)
CONVERSATION = [
    LLMMessage(role="user", content="성수에서 3만원으로 놀래"),
    LLMMessage(
        role="assistant",
        content="",
        tool_calls=[ToolCall("tu_1", "generate_course", {"region": "seoul-seongsu"})],
    ),
    LLMMessage(
        role="tool",
        tool_results=[
            ToolResult("tu_1", '{"ok": true}', name="generate_course"),
            ToolResult("tu_2", "boom", is_error=True, name="search_places"),
        ],
    ),
]


def test_anthropic_message_conversion() -> None:
    messages = to_anthropic_messages(CONVERSATION)
    assert [m["role"] for m in messages] == ["user", "assistant", "user"]
    assert messages[1]["content"] == [
        {"type": "tool_use", "id": "tu_1", "name": "generate_course", "input": {"region": "seoul-seongsu"}}
    ]
    results = messages[2]["content"]  # all tool results in ONE user message
    assert [r["tool_use_id"] for r in results] == ["tu_1", "tu_2"]
    assert "is_error" not in results[0] and results[1]["is_error"] is True

    native = [{"type": "thinking", "thinking": "", "signature": "sig"}, {"type": "text", "text": "짠!"}]
    echoed = to_anthropic_messages(
        [
            LLMMessage(
                role="assistant", content="짠!", provider_state={"provider": "anthropic", "content": native}
            )
        ]
    )
    assert echoed[0]["content"] is native  # echoed back unchanged


def test_anthropic_request_kwargs_per_tier() -> None:
    schema = {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]}
    request = LLMRequest(
        messages=CONVERSATION[:1], system="sys", tools=[TOOL], json_schema=schema, max_tokens=2048
    )
    smart = build_request_kwargs(request, "claude-opus-5")
    assert smart["output_config"] == {"effort": "low", "format": {"type": "json_schema", "schema": schema}}
    assert smart["tools"][0]["input_schema"] == TOOL.input_schema
    assert smart["system"] == "sys" and smart["max_tokens"] == 2048
    fast = build_request_kwargs(request, "claude-haiku-4-5")
    assert "effort" not in fast["output_config"]
    for kwargs in (smart, fast):
        assert "thinking" not in kwargs and "temperature" not in kwargs
        assert kwargs["messages"][-1]["role"] == "user"  # no assistant prefill


async def test_anthropic_missing_key() -> None:
    provider = AnthropicProvider(None)
    assert provider.available is False
    assert provider.model_for("smart") == "claude-opus-5" and provider.model_for("fast") == "claude-haiku-4-5"
    with pytest.raises(LLMNotConfiguredError):
        await provider.complete(LLMRequest(messages=CONVERSATION[:1]))


def test_openai_and_gemini_payloads() -> None:
    request = LLMRequest(messages=CONVERSATION, system="sys", tools=[TOOL], json_schema=TOOL.input_schema)
    payload = build_openai_payload(request, "gpt-4.1", stream=False)
    assert [m["role"] for m in payload["messages"]] == ["system", "user", "assistant", "tool", "tool"]
    assert payload["messages"][2]["tool_calls"][0]["function"]["arguments"] == '{"region": "seoul-seongsu"}'
    assert payload["response_format"]["json_schema"]["strict"] is True

    contents = to_gemini_contents(CONVERSATION)
    assert [c["role"] for c in contents] == ["user", "model", "user"]
    assert contents[2]["parts"][0]["functionResponse"]["name"] == "generate_course"
    assert "error" in contents[2]["parts"][1]["functionResponse"]["response"]
    assert "additionalProperties" not in sanitize_schema(TOOL.input_schema)
