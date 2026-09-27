"""docs/63 구경하는 가게: the 소품샵 · 캐릭터샵 option through the real API. The seed DB has no shops, so the
option must say so out loud — and a plain afternoon must not change or complain about its empty browse slot."""

from __future__ import annotations

import httpx

from tests.conftest import GENERATE_BODY

AFTERNOON = {"start_at": "2026-09-20T13:00:00+09:00", "budget_total": 60000, "alternatives": 0}


async def test_asked_for_shops_where_there_are_none_is_said_out_loud(client: httpx.AsyncClient) -> None:
    resp = await client.post("/v1/courses/generate", json={**GENERATE_BODY, **AFTERNOON, "extras": ["SHOP"]})
    assert resp.status_code == 200, resp.text
    course = resp.json()["courses"][0]
    assert course["stops"]  # the day is still planned
    warning = next(w for w in course["warnings"] if w["code"] == "EXTRA_UNAVAILABLE")
    assert warning["meta"] == {"extra": "SHOP", "label": "소품샵 · 캐릭터샵 구경", "vetoed": False}
    assert "가게" in warning["detail"]
    assert not [w for w in course["warnings"] if w["code"] == "SLOT_EMPTY"]  # one message, not two


async def test_a_plain_afternoon_without_shops_is_quiet(client: httpx.AsyncClient) -> None:
    resp = await client.post("/v1/courses/generate", json={**GENERATE_BODY, **AFTERNOON})
    assert resp.status_code == 200, resp.text
    course = resp.json()["courses"][0]
    codes = {w["code"] for w in course["warnings"]}
    assert "EXTRA_UNAVAILABLE" not in codes and "SLOT_EMPTY" not in codes


async def test_the_one_line_reads_a_shop_wish(client: httpx.AsyncClient) -> None:
    resp = await client.post("/v1/courses/options/parse", json={"text": "성수 소품샵 구경하고 싶어"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["extras"] == ["SHOP"] and body["errand"] is None
    assert body["matched"][0]["label"] == "소품샵 · 캐릭터샵 구경"
