"""docs/47: 한도가 있는 외부 API 호출을 센다 — 어느 API 인지 · 몇 % 인지 · 다 썼는지."""

from __future__ import annotations

import httpx
import pytest

from app.infra import api_usage
from app.infra.api_usage import provider_of, status_of


@pytest.mark.parametrize(
    ("url", "provider"),
    [
        ("https://apis.data.go.kr/B551011/KorService2/detailCommon2?contentId=1", "tourapi"),
        ("https://apis.data.go.kr/1360000/Other/list", "data_go_kr"),
        ("https://dapi.kakao.com/v2/local/search/keyword.json", "kakao_local"),
        ("https://openapi.naver.com/v1/search/blog.json", "naver_search"),
        ("https://api.pexels.com/v1/search", "pexels"),
        ("https://upload.wikimedia.org/x.jpg", None),  # not a quota'd API
        ("http://localhost:8000/v1/meta", None),
    ],
)
def test_provider_of(url: str, provider: str | None) -> None:
    assert provider_of(httpx.URL(url)) == provider


def test_status_thresholds() -> None:
    assert status_of(10, 1000, False) == "ok"
    assert status_of(800, 1000, False) == "warn"
    assert status_of(960, 1000, False) == "critical"
    assert status_of(10, 1000, True) == "exhausted"
    assert status_of(10, None, False) == "unknown"


def test_every_configured_quota_names_where_to_check() -> None:
    for provider, spec in api_usage.quotas().items():
        assert spec["period"] in {"day", "month"}, provider
        assert spec["name"], provider


@pytest.mark.asyncio
async def test_data_go_kr_exhaustion_is_read_from_the_body() -> None:
    request = httpx.Request("GET", "https://apis.data.go.kr/B551011/KorService2/areaBasedList2")
    body = b"<OpenAPI_ServiceResponse><returnReasonCode>22</returnReasonCode>LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR"
    assert await api_usage._exhausted("tourapi", httpx.Response(200, content=body, request=request))
    ok = httpx.Response(200, json={"response": {}}, request=request)
    assert not await api_usage._exhausted("tourapi", ok)
    assert await api_usage._exhausted("kakao_local", httpx.Response(429, request=request))
