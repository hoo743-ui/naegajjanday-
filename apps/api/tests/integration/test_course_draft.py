"""The course as a draft the user edits: pin stops and plan again, look at a few options for one stop and
pick one, nudge the whole day with a wish."""

from __future__ import annotations

import httpx

from tests.integration.test_courses import generate


def ids(course: dict) -> list[str]:
    return [s["place"]["id"] for s in course["stops"]]


def codes(course: dict) -> list[str]:
    return [w["code"] for w in course["warnings"]]


class TestKeepPlaces:
    async def test_pinned_stops_stay_and_the_rest_is_planned_around_them(
        self, client: httpx.AsyncClient
    ) -> None:
        first = (await generate(client, alternatives=0)).json()["courses"][0]
        old = ids(first)
        keep = [old[0], old[2]]
        # the web sends the whole old course as excluded and the pinned stops as kept: kept wins
        resp = await generate(
            client,
            alternatives=0,
            keep_place_ids=keep,
            preferences={"exclude_place_ids": old},
        )
        assert resp.status_code == 200, resp.text
        course = resp.json()["courses"][0]
        now = ids(course)
        assert set(keep) <= set(now)
        assert old[1] not in now  # the stop that was not pinned is replaced
        assert now.index(keep[0]) < now.index(keep[1])  # the old order holds
        assert "KEPT_PLACE_DROPPED" not in codes(course)
        assert course["totals"]["price"] == sum(s["est_price"] for s in course["stops"])

    async def test_alternatives_all_hold_the_pinned_stop(self, client: httpx.AsyncClient) -> None:
        first = (await generate(client, alternatives=0)).json()["courses"][0]
        pinned = ids(first)[1]
        courses = (await generate(client, alternatives=2, keep_place_ids=[pinned])).json()["courses"]
        assert all(pinned in ids(c) for c in courses)

    async def test_unknown_id_is_left_out_with_a_warning(self, client: httpx.AsyncClient) -> None:
        resp = await generate(client, alternatives=0, keep_place_ids=["no-such-place"])
        assert resp.status_code == 200, resp.text
        course = resp.json()["courses"][0]
        dropped = [w for w in course["warnings"] if w["code"] == "KEPT_PLACE_DROPPED"]
        assert len(dropped) == 1 and dropped[0]["meta"]["reason"] == "unknown"
        assert dropped[0]["meta"]["place_id"] == "no-such-place"

    async def test_a_pin_that_cannot_fit_is_dropped_with_its_name(self, client: httpx.AsyncClient) -> None:
        rich = (await generate(client, alternatives=0, budget_total=160000)).json()["courses"][0]
        dear = max(rich["stops"], key=lambda s: s["est_price"])
        assert dear["est_price"] > 0
        # a budget smaller than that one place for the pair: no course can hold it, but a course still comes
        resp = await generate(
            client,
            alternatives=0,
            budget_total=max(16000, dear["est_price"] // 2),
            keep_place_ids=[dear["place"]["id"]],
        )
        assert resp.status_code == 200, resp.text
        course = resp.json()["courses"][0]
        assert dear["place"]["id"] not in ids(course)
        dropped = next(w for w in course["warnings"] if w["code"] == "KEPT_PLACE_DROPPED")
        assert dropped["meta"]["reason"] == "unfit" and dear["place"]["name"] in dropped["detail"]

    async def test_at_most_six_pins(self, client: httpx.AsyncClient) -> None:
        resp = await generate(client, keep_place_ids=[f"p{i}" for i in range(7)])
        assert resp.status_code == 422


class TestCandidates:
    async def test_shape_limit_and_nothing_already_in_the_course(self, client: httpx.AsyncClient) -> None:
        course = (await generate(client, alternatives=0)).json()["courses"][0]
        url = f"/v1/courses/{course['id']}/stops/2/candidates"
        resp = await client.get(url)
        assert resp.status_code == 200, resp.text
        items = resp.json()["items"]
        assert 1 <= len(items) <= 3
        current = course["stops"][1]
        for item in items:
            assert set(item) == {"place", "role", "est_price", "price_delta", "walk_min_delta", "line"}
            assert item["place"]["id"] not in ids(course)
            assert item["role"] == current["role"]
            assert item["price_delta"] == item["est_price"] - current["est_price"]
            assert isinstance(item["walk_min_delta"], int)  # a walking course
            assert item["line"] and len(item["line"]) <= 40
            # the budget still holds with this place instead
            assert course["totals"]["price"] + item["price_delta"] <= 40000
        one = (await client.get(url, params={"limit": 1})).json()["items"]
        assert len(one) == 1 and one[0]["place"]["id"] == items[0]["place"]["id"]
        assert (await client.get(url, params={"limit": 6})).status_code == 422
        assert (await client.get(url, params={"limit": 0})).status_code == 422

    async def test_bad_position_or_course_is_404(self, client: httpx.AsyncClient) -> None:
        course = (await generate(client, alternatives=0)).json()["courses"][0]
        bad = await client.get(f"/v1/courses/{course['id']}/stops/9/candidates")
        assert (bad.status_code, bad.json()["code"]) == (404, "STOP_NOT_FOUND")
        gone = await client.get("/v1/courses/nope/stops/1/candidates")
        assert (gone.status_code, gone.json()["code"]) == (404, "COURSE_NOT_FOUND")

    async def test_anyone_who_can_read_may_look_but_only_editors_swap(
        self, client: httpx.AsyncClient
    ) -> None:
        course = (await generate(client, alternatives=0)).json()["courses"][0]
        client.stranger()  # type: ignore[attr-defined]
        items = (await client.get(f"/v1/courses/{course['id']}/stops/2/candidates")).json()["items"]
        assert items
        resp = await client.post(
            f"/v1/courses/{course['id']}/swap", json={"position": 2, "place_id": items[0]["place"]["id"]}
        )
        assert resp.status_code == 403


class TestSwapToPlace:
    async def test_the_picked_place_takes_the_stop(self, client: httpx.AsyncClient) -> None:
        course = (await generate(client, alternatives=0)).json()["courses"][0]
        items = (await client.get(f"/v1/courses/{course['id']}/stops/2/candidates")).json()["items"]
        pick = items[-1]
        resp = await client.post(
            f"/v1/courses/{course['id']}/swap",
            json={"position": 2, "strategy": "cheaper", "place_id": pick["place"]["id"]},  # strategy ignored
        )
        assert resp.status_code == 200, resp.text
        swapped = resp.json()
        assert ids(swapped) == [ids(course)[0], pick["place"]["id"], ids(course)[2]]
        assert swapped["stops"][1]["est_price"] == pick["est_price"]
        assert swapped["totals"]["price"] == course["totals"]["price"] + pick["price_delta"]
        assert swapped["totals"]["price"] == sum(s["est_price"] for s in swapped["stops"])
        persisted = (await client.get(f"/v1/courses/{course['id']}")).json()["course"]
        assert ids(persisted) == ids(swapped)

    async def test_a_place_that_does_not_pass_is_refused(self, client: httpx.AsyncClient) -> None:
        course = (await generate(client, alternatives=0)).json()["courses"][0]
        url = f"/v1/courses/{course['id']}/swap"
        for place_id in (ids(course)[0], ids(course)[1], "no-such-place"):  # in the course already / unknown
            resp = await client.post(url, json={"position": 2, "place_id": place_id})
            assert (resp.status_code, resp.json()["code"]) == (422, "CANDIDATE_NOT_ELIGIBLE")
            assert resp.json()["meta"]["place_id"] == place_id
        # nothing changed
        assert ids((await client.get(f"/v1/courses/{course['id']}")).json()["course"]) == ids(course)


class TestWishes:
    async def test_quiet_leaves_out_the_pub(self, client: httpx.AsyncClient) -> None:
        loud = (await generate(client, budget_total=160000, alternatives=0)).json()["courses"][0]
        assert "BAR" in [s["role"] for s in loud["stops"]]
        resp = await generate(client, budget_total=160000, alternatives=0, wishes=["quiet"])
        assert resp.status_code == 200, resp.text
        quiet = resp.json()["courses"][0]
        assert "BAR" not in [s["role"] for s in quiet["stops"]]
        # asking for a drink by name still gets one
        drink = await generate(client, budget_total=160000, alternatives=0, wishes=["quiet"], extras=["BAR"])
        assert "BAR" in [s["role"] for s in drink.json()["courses"][0]["stops"]]

    async def test_indoor_is_the_rainy_day_plan(self, client: httpx.AsyncClient) -> None:
        resp = await generate(client, alternatives=0, wishes=["indoor"])
        assert resp.status_code == 200, resp.text
        course = resp.json()["courses"][0]
        assert "ATTRACTION" not in [s["role"] for s in course["stops"]]
        assert [s["place"]["name"] for s in course["stops"] if "야외" in s["place"]["tags"]] == []
        echo = (await client.get(f"/v1/courses/{course['id']}")).json()["request"]
        assert echo["conditions"] == []  # said as a wish, not as the weather

    async def test_free_puts_more_of_the_day_at_no_cost(self, client: httpx.AsyncClient) -> None:
        body = {"budget_total": 160000, "alternatives": 0}
        plain = (await generate(client, **body)).json()["courses"][0]
        resp = await generate(client, **body, wishes=["free"])
        assert resp.status_code == 200, resp.text
        free = resp.json()["courses"][0]

        def at_no_cost(course: dict) -> int:
            return sum(1 for s in course["stops"] if s["est_price"] == 0)

        assert at_no_cost(free) >= at_no_cost(plain) and at_no_cost(free) >= 1
        assert free["totals"]["price"] <= plain["totals"]["price"]

    async def test_photo_is_accepted(self, client: httpx.AsyncClient) -> None:
        # the seed places carry no photos: the pull itself is covered in tests/unit/test_preference.py
        resp = await generate(client, alternatives=0, wishes=["photo", "quiet", "free", "indoor", "value"])
        assert resp.status_code == 200, resp.text
        bad = await generate(client, alternatives=0, wishes=["loud"])
        assert bad.status_code == 422

    async def test_interpret_says_the_new_wishes_back(self, client: httpx.AsyncClient) -> None:
        resp = await client.post(
            "/v1/courses/interpret", json={"wishes": ["quiet", "indoor", "photo", "free"]}
        )
        assert resp.status_code == 200, resp.text
        lines = [s["text"] for s in resp.json()["summary"] if s["kind"] == "wish"]
        assert lines == ["조용한 곳 위주", "실내 위주", "사진이 있는 곳 위주", "무료로 들를 곳 더"]


class TestReasonShort:
    async def test_every_stop_has_a_short_line_or_none(self, client: httpx.AsyncClient) -> None:
        course = (await generate(client, alternatives=0)).json()["courses"][0]
        detail = (await client.get(f"/v1/courses/{course['id']}")).json()["course"]
        shorts = [s["reason_short"] for s in detail["stops"]]
        assert any(shorts)
        assert all(s is None or 0 < len(s) <= 40 for s in shorts)
        assert [s["reason_short"] for s in course["stops"]] == shorts
