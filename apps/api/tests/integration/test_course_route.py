"""GET /v1/courses/{id}/route — the generated course as a checked route (docs/27)."""

from __future__ import annotations

from itertools import pairwise

import httpx

from tests.conftest import GENERATE_BODY


async def test_route_of_a_generated_course(client: httpx.AsyncClient) -> None:
    gen = await client.post("/v1/courses/generate", json=GENERATE_BODY)
    assert gen.status_code == 200, gen.text
    course = gen.json()["courses"][0]

    resp = await client.get(f"/v1/courses/{course['id']}/route")
    assert resp.status_code == 200, resp.text
    route = resp.json()

    assert route["course_id"] == course["id"]
    assert [s["sequence"] for s in route["stops"]] == [s["position"] for s in course["stops"]]
    assert [s["place_id"] for s in route["stops"]] == [s["place"]["id"] for s in course["stops"]]
    assert len(route["legs"]) == len(course["stops"]) - 1
    for leg, (a, b) in zip(route["legs"], pairwise(course["stops"]), strict=True):
        assert (leg["from_seq"], leg["to_seq"]) == (a["position"], b["position"])
        # no router in tests → the engine's own figures, labelled as an estimate (never invented)
        assert leg["source"] == "estimate" and leg["geometry"] == "straight"
        assert leg["duration_min"] == max(1, b["from_prev"]["travel_min"])
        assert leg["distance_m"] == b["from_prev"]["distance_m"]
        assert leg["path"][0] == [a["place"]["lat"], a["place"]["lng"]]
    assert route["totals"]["measured"] is False
    assert route["providers"] == {"walk": "estimate", "car": "estimate", "transit": "estimate"}
    assert route["feasible"] is True, route["issues"]


async def test_route_of_a_missing_course_is_404(client: httpx.AsyncClient) -> None:
    resp = await client.get("/v1/courses/00000000-0000-4000-8000-000000000000/route")
    assert resp.status_code == 404
