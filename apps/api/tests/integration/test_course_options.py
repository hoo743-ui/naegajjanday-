"""선택지가 늘어도 어지럽지 않게 (docs/59 #2): the one-line input and the wizard's last-choice defaults."""

from __future__ import annotations

import httpx

from app.domain.recommendation.option_text import last_choices
from tests.conftest import GENERATE_BODY


async def test_one_line_becomes_the_request_options(client: httpx.AsyncClient) -> None:
    resp = await client.post("/v1/courses/options/parse", json={"text": "술은 빼고 영화 보고 비 온대"})
    assert resp.status_code == 200, resp.text
    got = resp.json()
    assert got["extras"] == ["MOVIE"] and got["conditions"] == ["rain"] and got["declined"] == ["BAR"]
    assert got["errand"] is None
    assert [m["key"] for m in got["matched"]] == ["BAR", "MOVIE", "rain"]
    assert got["matched"][0]["declined"] is True and got["matched"][1]["label"] == "영화 한 편"


async def test_parse_rejects_an_empty_or_long_line(client: httpx.AsyncClient) -> None:
    assert (await client.post("/v1/courses/options/parse", json={"text": ""})).status_code == 422
    assert (await client.post("/v1/courses/options/parse", json={"text": "가" * 121})).status_code == 422


async def test_last_choices_needs_a_sign_in(client: httpx.AsyncClient) -> None:
    assert (await client.get("/v1/me/last-choices")).status_code == 401


async def test_last_choices_are_the_last_request(
    client: httpx.AsyncClient, user_headers: dict[str, str]
) -> None:
    body = {**GENERATE_BODY, "alternatives": 0, "extras": ["BAR"], "conditions": ["rain"]}
    resp = await client.post("/v1/courses/generate", json=body, headers=user_headers)
    assert resp.status_code == 200, resp.text
    got = (await client.get("/v1/me/last-choices", headers=user_headers)).json()
    assert got["purpose"] and got["budget_total"] and got["party_size"]
    assert got["extras"] == ["BAR"]
    assert "conditions" not in got  # rain was that day's, not a choice to carry over


def test_last_choices_keep_only_a_plain_neighbourhood() -> None:
    base = {
        "purpose": "date",
        "party_size": 2,
        "budget_total": 60000,
        "extras": ["BAR", "NOPE"],
        "conditions": ["rain"],
    }
    assert last_choices({**base, "region": "a"}, ["BAR"])["region"] == "a"
    assert "region" not in last_choices({**base, "region": "a", "errand": {"name": "x"}}, ["BAR"])
    assert "region" not in last_choices({**base, "region": "a", "regions": ["b", "a"]}, ["BAR"])
    got = last_choices(base, ["BAR"])
    assert got["extras"] == ["BAR"] and "conditions" not in got
