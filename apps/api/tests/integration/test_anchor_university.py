"""docs/34: a university campus as the anchor of the day — the same engine, a few knobs."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

from app.core.deps import Container
from app.services.ingestion_runner import ingest
from tests.conftest import GENERATE_BODY

DAY = "2026-09-20"  # GENERATE_BODY's date
# Two sample campuses next to the Hongdae seed area (fictional, like the rest of the seed data):
# one ~370 m from the seed street festival, one far enough from it that its day has no festival.
CAMPUSES = {
    "places": [
        {
            "external_id": "anchor-test-hongik",
            "name": "샘플대학교",
            "category": "attraction.campus",
            "lat": 37.5525,
            "lng": 126.9250,
            "address": "서울 마포구 샘플대학로 1 (샘플)",
            "road_address": None,
            "is_free": True,
            "price_per_person": 0,
        },
        {
            "external_id": "anchor-test-quiet",
            "name": "조용한샘플대학교",
            "category": "attraction.campus",
            "lat": 37.5640,
            "lng": 126.9310,
            "address": "서울 서대문구 샘플캠퍼스길 2 (샘플)",
            "road_address": None,
            "is_free": True,
            "price_per_person": 0,
        },
    ],
    "events": [],
}


@pytest_asyncio.fixture
async def campuses(container: Container, tmp_path: Path) -> dict[str, str]:
    """Two campuses, loaded through the real file pipeline (idempotent across tests)."""
    path = tmp_path / "campuses.json"
    path.write_text(
        # filed under the district, not 홍대: the hotspot's own place count is asserted elsewhere
        json.dumps({"region": "seoul-mapo", "provider": "file", **CAMPUSES}, ensure_ascii=False),
        encoding="utf-8",
    )
    _, report = await ingest(
        container.db, container.settings, provider_name="file", region_slug=None, path=path
    )
    assert report.failed == 0, report.errors
    return {}


async def search(client: httpx.AsyncClient, q: str) -> dict:
    resp = await client.get("/v1/meta/universities", params={"q": q})
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert items, f"no campus for {q}"
    return items[0]


async def generate(client: httpx.AsyncClient, **overrides: object) -> httpx.Response:
    body = {**GENERATE_BODY, **overrides}
    if "anchor" in overrides:
        body.pop("region", None)
    return await client.post("/v1/courses/generate", json=body)


@pytest.mark.usefixtures("campuses")
class TestUniversityAnchor:
    async def test_search_and_the_purposes_of_a_campus_day(self, client: httpx.AsyncClient) -> None:
        campus = await search(client, "샘플대")
        assert campus["name"] == "샘플대학교" and campus["id"]
        plain = [p["code"] for p in (await client.get("/v1/meta/purposes")).json()["items"]]
        assert not {"campus", "campus_food", "festival"} & set(plain)  # only around a campus
        around = [
            p["code"] for p in (await client.get("/v1/meta/purposes?context=university")).json()["items"]
        ]
        assert around[:3] == ["campus", "campus_food", "festival"]
        assert {"date", "friends"} <= set(around)

    async def test_a_campus_only_purpose_needs_a_campus(self, client: httpx.AsyncClient) -> None:
        resp = await generate(client, purpose="campus")
        assert resp.status_code == 422, resp.text
        missing = await generate(client, anchor={"kind": "university", "id": "no-such-campus"})
        assert missing.status_code == 404

    async def test_campus_walk_is_the_first_stop_and_the_day_stays_around_it(
        self, client: httpx.AsyncClient
    ) -> None:
        campus = await search(client, "샘플대학교")
        resp = await generate(
            client,
            anchor={"kind": "university", "id": campus["id"]},
            purpose="campus",
            start_at=f"{DAY}T11:00:00+09:00",
            alternatives=0,
        )
        assert resp.status_code == 200, resp.text
        course = resp.json()["courses"][0]
        ids = [s["place"]["id"] for s in course["stops"]]
        assert campus["id"] in ids, "the campus itself is a stop of a campus day"
        stop = next(s for s in course["stops"] if s["place"]["id"] == campus["id"])
        assert stop["role"] == "ATTRACTION" and stop["est_price"] == 0
        assert course["totals"]["price"] <= GENERATE_BODY["budget_total"]
        detail = (await client.get(f"/v1/courses/{course['id']}")).json()["request"]
        assert detail["anchor"]["id"] == campus["id"] and detail["anchor"]["name"] == "샘플대학교"
        assert detail["context"] in ("university", "festival")
        assert detail["origin_label"] == "샘플대학교"

    async def test_campus_food_leaves_the_campus_out(self, client: httpx.AsyncClient) -> None:
        campus = await search(client, "샘플대학교")
        resp = await generate(
            client, anchor={"kind": "university", "id": campus["id"]}, purpose="campus_food", alternatives=0
        )
        assert resp.status_code == 200, resp.text
        assert campus["id"] not in [s["place"]["id"] for s in resp.json()["courses"][0]["stops"]]

    async def test_the_campus_festival_is_the_core_of_a_festival_day(
        self, client: httpx.AsyncClient, admin_headers: dict[str, str]
    ) -> None:
        campus = await search(client, "샘플대학교")
        created = await client.post(
            "/v1/admin/events",
            headers=admin_headers,
            json={
                "region": "seoul-mapo",  # not 홍대: its event list is asserted elsewhere
                "title": "샘플대 가을 축제",
                "category": "culture.festival",
                "university": campus["id"],
                "starts_on": DAY,
                "ends_on": DAY,
                "start_time": "18:00",
                "end_time": "22:00",
                "priority": 10,
                "is_free": True,
            },
        )
        assert created.status_code in (200, 201), created.text
        assert created.json()["university"] == campus["id"]
        try:
            await self._festival_day(client, campus)
        finally:  # the test database is shared by the whole session
            await client.delete(f"/v1/admin/events/{created.json()['id']}", headers=admin_headers)

    async def _festival_day(self, client: httpx.AsyncClient, campus: dict) -> None:
        resp = await generate(
            client,
            anchor={"kind": "university", "id": campus["id"]},
            purpose="festival",
            start_at=f"{DAY}T16:00:00+09:00",
            alternatives=0,
        )
        assert resp.status_code == 200, resp.text
        course = resp.json()["courses"][0]
        festival = [s for s in course["stops"] if s["place"].get("kind") == "event"]
        assert [s["place"]["name"] for s in festival] == ["샘플대 가을 축제"]
        # its hours are its opening hours: the engine keeps the stop inside 18:00~22:00
        assert "18:00" <= festival[0]["arrive_at"][11:16] < "22:00"
        detail = (await client.get(f"/v1/courses/{course['id']}")).json()["request"]
        assert detail["context"] == "festival" and detail["anchor"]["festival"] == "샘플대 가을 축제"

    async def test_no_festival_that_day_falls_back_to_a_campus_day(self, client: httpx.AsyncClient) -> None:
        campus = await search(client, "조용한샘플")
        resp = await generate(
            client,
            anchor={"kind": "university", "id": campus["id"]},
            purpose="festival",
            start_at=f"{DAY}T16:00:00+09:00",
            alternatives=0,
        )
        assert resp.status_code == 200, resp.text
        course = resp.json()["courses"][0]
        assert course["stops"], "no festival is no reason to fail"
        assert "FESTIVAL_NOT_FOUND" in [w["code"] for w in course["warnings"]]
        # …and the campus itself anchors the day instead (docs/34 §6)
        assert campus["id"] in [s["place"]["id"] for s in course["stops"]]

    async def test_a_reroll_keeps_the_campus(self, client: httpx.AsyncClient) -> None:
        campus = await search(client, "샘플대학교")
        first = (
            await generate(
                client, anchor={"kind": "university", "id": campus["id"]}, purpose="date", alternatives=0
            )
        ).json()["courses"][0]
        echo = (await client.get(f"/v1/courses/{first['id']}")).json()["request"]
        again = await generate(
            client,
            anchor={"kind": echo["anchor"]["kind"], "id": echo["anchor"]["id"]},
            purpose="date",
            alternatives=0,
            preferences={"exclude_place_ids": [s["place"]["id"] for s in first["stops"]]},
        )
        assert again.status_code == 200, again.text
        detail = (await client.get(f"/v1/courses/{again.json()['courses'][0]['id']}")).json()["request"]
        assert detail["anchor"]["id"] == campus["id"]
