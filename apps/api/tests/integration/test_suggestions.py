"""Money left over is an offer to make ("how about this?"), and the offer can be put into the course."""

from __future__ import annotations

import httpx

from tests.conftest import GENERATE_BODY


async def course_with_money_left(client: httpx.AsyncClient) -> dict:
    # a short lunch on a dinner-sized budget: most of the money stays in the pocket
    resp = await client.post(
        "/v1/courses/generate",
        json={**GENERATE_BODY, "budget_total": 120000, "start_at": "2026-09-22T12:00:00+09:00",
              "duration_min": 120, "alternatives": 0},
    )  # fmt: skip
    assert resp.status_code == 200, resp.text
    return resp.json()["courses"][0]


class TestSuggestions:
    async def test_what_is_offered_fits_the_money_the_walk_and_the_course(
        self, client: httpx.AsyncClient
    ) -> None:
        course = await course_with_money_left(client)
        left = 120000 - course["totals"]["price"]
        body = (await client.get(f"/v1/courses/{course['id']}/suggestions")).json()
        assert body["budget_left"] == left and body["items"], body
        in_course = {s["place"]["id"] for s in course["stops"]}
        roles_in_course = {s["role"] for s in course["stops"]}
        for item in body["items"]:
            assert item["est_price"] <= left
            assert item["walk_min"] <= 12
            assert item["place"]["id"] not in in_course
            assert item["role"] not in roles_in_course  # a second café is not a suggestion
            assert item["line"]
        assert len({i["role"] for i in body["items"]}) == len(body["items"])  # one per kind of place

    async def test_nothing_is_offered_when_the_budget_is_spent(self, client: httpx.AsyncClient) -> None:
        tight = (await client.post("/v1/courses/generate", json={**GENERATE_BODY, "alternatives": 0})).json()
        course = tight["courses"][0]
        body = (await client.get(f"/v1/courses/{course['id']}/suggestions")).json()
        if 40000 - course["totals"]["price"] < 10000:  # under 5,000 a head: not worth an offer
            assert body["items"] == []

    async def test_an_offer_can_be_added_and_the_receipt_follows(self, client: httpx.AsyncClient) -> None:
        course = await course_with_money_left(client)
        offer = (await client.get(f"/v1/courses/{course['id']}/suggestions")).json()["items"][0]
        added = await client.post(
            f"/v1/courses/{course['id']}/stops", json={"place_id": offer["place"]["id"]}
        )
        assert added.status_code == 200, added.text
        after = added.json()
        assert [s["place"]["id"] for s in after["stops"]] == [
            *[s["place"]["id"] for s in course["stops"]],
            offer["place"]["id"],
        ]
        assert after["totals"]["price"] == course["totals"]["price"] + offer["est_price"]
        assert after["totals"]["price"] <= 120000
        last, before_last = after["stops"][-1], after["stops"][-2]
        assert last["arrive_at"] >= before_last["leave_at"]
        # the same place cannot be added twice, and a place that was never offered cannot be added at all
        again = await client.post(
            f"/v1/courses/{course['id']}/stops", json={"place_id": offer["place"]["id"]}
        )
        assert again.status_code == 422
        stranger = await client.post(f"/v1/courses/{course['id']}/stops", json={"place_id": "not-a-place"})
        assert stranger.status_code == 422
