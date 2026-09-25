"""Money left over is an offer to make ("how about this?"), and the offer can be put into the course."""

from __future__ import annotations

import httpx
import pytest

from app.domain.recommendation.style import suggestion_rules
from app.services import course_service
from tests.conftest import GENERATE_BODY


@pytest.fixture(autouse=True)
def no_underspent_top_up(monkeypatch: pytest.MonkeyPatch) -> None:
    """These tests need a course with money left: the docs/49 top-up of an underspent course stays off
    (TestTopUp turns it back on where it is the subject)."""
    rules = suggestion_rules()
    monkeypatch.setattr(
        course_service, "suggestion_rules", lambda: {**rules, "top_up": {**rules["top_up"], "below_use": 0.0}}
    )


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


class TestTopUp:
    """One place is not a course: what would have been offered is put in, and the course says so."""

    async def test_a_course_that_came_out_too_short_is_topped_up_and_says_so(
        self, client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        plain = await course_with_money_left(client)
        assert "TOPPED_UP" not in [w["code"] for w in plain["warnings"]]  # two stops or more: left alone

        rules = suggestion_rules()
        short_of = len(plain["stops"]) + 1  # "too short" now means: what this request normally gives
        monkeypatch.setattr(
            course_service,
            "suggestion_rules",
            lambda: {
                **rules,
                "top_up": {**rules["top_up"], "below_stops": short_of, "max_added": 1, "below_use": 0.0},
            },
        )
        # a start ten minutes later: the answer to the first request is cached by its body
        resp = await client.post(
            "/v1/courses/generate",
            json={**GENERATE_BODY, "budget_total": 120000, "start_at": "2026-09-22T12:10:00+09:00",
                  "duration_min": 120, "alternatives": 0},
        )  # fmt: skip
        assert resp.status_code == 200, resp.text
        course = resp.json()["courses"][0]
        notes = [w for w in course["warnings"] if w["code"] == "TOPPED_UP"]
        assert len(notes) == 1 and len(course["stops"]) == len(plain["stops"]) + 1
        added = course["stops"][-1]
        assert added["place"]["id"] == notes[0]["meta"]["place_id"]
        assert added["place"]["name"] in notes[0]["detail"]
        assert course["totals"]["price"] == sum(s["est_price"] for s in course["stops"]) <= 120000
        assert added["arrive_at"] >= course["stops"][-2]["leave_at"]
        # what was returned is what was saved
        saved = (await client.get(f"/v1/courses/{course['id']}")).json()["course"]
        assert [s["place"]["id"] for s in saved["stops"]] == [s["place"]["id"] for s in course["stops"]]

        # the note goes when the place goes
        swapped = await client.post(f"/v1/courses/{course['id']}/swap", json={"position": added["position"]})
        if swapped.status_code == 200 and swapped.json()["stops"][-1]["place"]["id"] != added["place"]["id"]:
            assert "TOPPED_UP" not in [w["code"] for w in swapped.json()["warnings"]]

    async def test_an_underspent_course_is_filled_before_anyone_sees_it(
        self, client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # docs/49: most of 120,000 won left on a two-hour lunch — one more place goes in, and it says why
        plain = await course_with_money_left(client)
        assert plain["totals"]["price"] < 0.6 * 120000
        assert plain["totals"]["leftover"]["band"] == "underspent" and plain["totals"]["leftover"]["text"]
        rules = suggestion_rules()
        monkeypatch.setattr(
            course_service,
            "suggestion_rules",
            lambda: {**rules, "top_up": {**rules["top_up"], "below_stops": 0, "max_added": 1}},
        )
        resp = await client.post(
            "/v1/courses/generate",
            json={**GENERATE_BODY, "budget_total": 120000, "start_at": "2026-09-22T12:20:00+09:00",
                  "duration_min": 120, "alternatives": 0},
        )  # fmt: skip
        course = resp.json()["courses"][0]
        notes = [w for w in course["warnings"] if w["code"] == "TOPPED_UP"]
        assert len(notes) == 1 and "예산이 많이 남아서" in notes[0]["detail"]
        assert course["totals"]["price"] <= 120000

    async def test_an_underspent_night_is_not_filled(
        self, client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # a night out is cut short on purpose (docs/48): its leftover is explained, not filled with karaoke
        rules = suggestion_rules()
        monkeypatch.setattr(
            course_service,
            "suggestion_rules",
            lambda: {**rules, "top_up": {**rules["top_up"], "below_stops": 0, "max_added": 2}},
        )
        resp = await client.post(
            "/v1/courses/generate",
            json={**GENERATE_BODY, "budget_total": 120000, "start_at": "2026-09-22T22:00:00+09:00",
                  "alternatives": 0},
        )  # fmt: skip
        assert resp.status_code == 200, resp.text
        course = resp.json()["courses"][0]
        assert not [w for w in course["warnings"] if w["code"] == "TOPPED_UP"]
