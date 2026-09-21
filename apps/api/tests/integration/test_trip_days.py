"""A trip is kept whole: planning one day again, or saving one day, never tears it apart.
And what was asked for by name ("a drink") is never dropped without a word."""

from __future__ import annotations

import httpx

from tests.conftest import GENERATE_BODY

TRIP = {"nights": 1, "budget_total": 200000, "start_at": "2026-09-22T14:00:00+09:00"}


async def generate(client: httpx.AsyncClient, **overrides: object) -> httpx.Response:
    return await client.post("/v1/courses/generate", json={**GENERATE_BODY, **overrides})


async def detail(client: httpx.AsyncClient, course_id: str, **kwargs: object) -> dict:
    return (await client.get(f"/v1/courses/{course_id}", **kwargs)).json()  # type: ignore[arg-type]


class TestPlanningOneDayAgain:
    async def test_the_new_course_takes_that_day_and_the_trip_stays_together(
        self, client: httpx.AsyncClient
    ) -> None:
        first, second = (await generate(client, **TRIP)).json()["courses"]
        echo = (await detail(client, first["id"]))["request"]

        again = await generate(
            client,
            budget_total=echo["budget_total"],
            start_at=echo["start_at"],
            duration_min=echo["duration_min"],
            alternatives=2,  # ignored: a day of a trip has no alternatives, the tabs are the days
            replaces=first["id"],
            preferences={"exclude_place_ids": [s["place"]["id"] for s in first["stops"]]},
        )
        assert again.status_code == 200, again.text
        courses = again.json()["courses"]
        assert len(courses) == 1 and courses[0]["label"] == "1일차"
        new = await detail(client, courses[0]["id"])
        assert (new["request"]["day"], new["request"]["days"]) == (1, 2)
        assert new["request"]["trip_budget_total"] == 200000
        # day one is still the first tab, and the old day one is gone from them
        assert [s["id"] for s in new["siblings"]] == [courses[0]["id"], second["id"]]
        assert [s["id"] for s in (await detail(client, second["id"]))["siblings"]] == [
            courses[0]["id"],
            second["id"],
        ]
        # nowhere day two already goes
        elsewhere = {s["place"]["id"] for s in second["stops"]}
        assert not elsewhere & {s["place"]["id"] for s in courses[0]["stops"]}

    async def test_an_ordinary_course_ignores_it(self, client: httpx.AsyncClient) -> None:
        plain = (await generate(client, alternatives=0)).json()["courses"][0]
        again = await generate(client, alternatives=1, replaces=plain["id"])
        assert again.status_code == 200 and len(again.json()["courses"]) == 2
        assert (await detail(client, plain["id"]))["course"]["id"] == plain["id"]

    async def test_a_saved_trip_stays_saved_when_a_day_changes(
        self, client: httpx.AsyncClient, user_headers: dict[str, str]
    ) -> None:
        first, second = (await generate(client, **TRIP)).json()["courses"]
        saved = await client.post(f"/v1/courses/{first['id']}/save", headers=user_headers)
        assert saved.status_code == 200
        # saving one day keeps the whole trip: the other day would be swept away otherwise
        mine = (await client.get("/v1/me/courses", headers=user_headers)).json()["items"]
        trip = {first["id"], second["id"]}  # the account is shared with other tests: look at this trip only
        assert {(c["id"], c["day"], c["days"]) for c in mine if c["id"] in trip} == {
            (first["id"], 1, 2),
            (second["id"], 2, 2),
        }

        echo = (await detail(client, second["id"], headers=user_headers))["request"]
        again = await client.post(
            "/v1/courses/generate",
            headers=user_headers,
            json={**GENERATE_BODY, "budget_total": echo["budget_total"], "start_at": echo["start_at"],
                  "duration_min": echo["duration_min"], "replaces": second["id"]},
        )  # fmt: skip
        assert again.status_code == 200, again.text
        new_id = again.json()["courses"][0]["id"]
        mine = (await client.get("/v1/me/courses", headers=user_headers)).json()["items"]
        assert {c["id"] for c in mine if c["id"] in {*trip, new_id}} == {first["id"], new_id}

    async def test_someone_else_may_not_replace_a_day_of_my_trip(
        self, client: httpx.AsyncClient, user_headers: dict[str, str]
    ) -> None:
        first, _ = (await generate(client, **TRIP)).json()["courses"]
        await client.post(f"/v1/courses/{first['id']}/save", headers=user_headers)
        resp = await generate(client, replaces=first["id"])
        assert resp.status_code == 403


class TestWhatWasAskedForByName:
    async def test_a_drink_that_does_not_fit_the_family_is_said_out_loud(
        self, client: httpx.AsyncClient
    ) -> None:
        resp = await generate(client, purpose="family", extras=["BAR"], alternatives=0, budget_total=160000)
        assert resp.status_code == 200, resp.text
        course = resp.json()["courses"][0]
        assert "BAR" not in [s["role"] for s in course["stops"]]
        warning = next(w for w in course["warnings"] if w["code"] == "EXTRA_UNAVAILABLE")
        assert warning["meta"] == {"extra": "BAR", "label": "술 한잔", "vetoed": True}
        assert warning["detail"]

    async def test_nothing_is_said_when_the_drink_is_there(self, client: httpx.AsyncClient) -> None:
        course = (await generate(client, extras=["BAR"], alternatives=0, budget_total=160000)).json()[
            "courses"
        ][0]
        assert "BAR" in [s["role"] for s in course["stops"]]
        assert [w for w in course["warnings"] if w["code"] == "EXTRA_UNAVAILABLE"] == []
