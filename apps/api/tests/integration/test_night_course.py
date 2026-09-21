"""After dark there is still a course: what the sign says is open, and what has no door."""

from __future__ import annotations

import json
from datetime import datetime

import httpx

from app.domain.recommendation.budget import evening_minute, time_band_for
from app.infra.default_hours import HOURS_PATH, get_default_hours
from tests.conftest import GENERATE_BODY

RULES = json.loads(HOURS_PATH.read_text(encoding="utf-8"))["by_name"]


def test_the_band_after_the_kitchens_close_is_night() -> None:
    assert time_band_for(datetime(2026, 9, 22, 20, 59), None) == "evening"
    assert time_band_for(datetime(2026, 9, 22, 21, 0), None) == "night"
    assert time_band_for(datetime(2026, 9, 23, 2, 0), 600) == "night"  # never a "full day" from 2 a.m.
    assert time_band_for(datetime(2026, 9, 23, 5, 0), None) == "lunch"


def test_one_in_the_morning_is_still_the_evening_before() -> None:
    # "a drink, from 17:00" (1020) was refused at 00:01 (minute 1): nothing to offer after midnight
    assert evening_minute(datetime(2026, 9, 22, 16, 59)) == 1019
    assert evening_minute(datetime(2026, 9, 22, 23, 59)) == 1439
    assert evening_minute(datetime(2026, 9, 23, 0, 1)) == 1441
    assert evening_minute(datetime(2026, 9, 23, 4, 59)) == 1739
    assert evening_minute(datetime(2026, 9, 23, 5, 0)) == 300  # the morning starts here


def test_a_sign_that_says_so_beats_what_the_trade_usually_does() -> None:
    hours = get_default_hours()
    round_the_clock, late, outdoors = RULES[0], RULES[1], RULES[2]
    assert hours.for_category("food.korean")  # an ordinary kitchen closes in the evening
    assert hours.for_place("food.korean", f"x {round_the_clock['words'][0]} y") == ()  # () = never closed
    late_hours = hours.for_place("food.korean", f"x{late['words'][0]}")
    assert late_hours and late_hours[0].close_min > 1440  # past midnight
    assert hours.for_place("cafe", f"x{late['words'][0]}") == hours.for_category(
        "cafe"
    )  # rule is food/bar only
    assert hours.for_place("attraction", f"x {outdoors['words'][0]}") == ()
    assert hours.for_place("attraction", "x") == hours.for_category("attraction")


class TestNightCourse:
    async def test_two_in_the_morning_gets_a_course_and_an_honest_note(
        self, client: httpx.AsyncClient
    ) -> None:
        resp = await client.post(
            "/v1/courses/generate",
            json={**GENERATE_BODY, "start_at": "2026-09-23T02:00:00+09:00", "alternatives": 0},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["meta"]["template"].endswith("-night")
        course = body["courses"][0]
        assert course["stops"]
        assert "NIGHT_HOURS_ESTIMATED" in [w["code"] for w in course["warnings"]]
        # the clock decides, not the request: it is not echoed as something the user chose
        echo = (await client.get(f"/v1/courses/{course['id']}")).json()["request"]
        assert echo["conditions"] == []

    async def test_the_note_survives_changing_the_course(self, client: httpx.AsyncClient) -> None:
        """Hours are still guessed after a place is moved or swapped: the note is about the hour, not the stops."""
        resp = await client.post(
            "/v1/courses/generate",
            json={**GENERATE_BODY, "start_at": "2026-09-23T02:00:00+09:00", "alternatives": 0},
        )
        course = resp.json()["courses"][0]
        order = [s["position"] for s in course["stops"]]
        if len(order) > 1:
            moved = await client.post(f"/v1/courses/{course['id']}/reorder", json={"order": order[::-1]})
            assert moved.status_code == 200, moved.text
            assert "NIGHT_HOURS_ESTIMATED" in [w["code"] for w in moved.json()["warnings"]]
        swapped = await client.post(f"/v1/courses/{course['id']}/swap", json={"position": order[0]})
        if swapped.status_code == 200:  # 409 when there is nothing else open at that hour
            assert "NIGHT_HOURS_ESTIMATED" in [w["code"] for w in swapped.json()["warnings"]]
        saved = (await client.get(f"/v1/courses/{course['id']}")).json()["course"]
        assert "NIGHT_HOURS_ESTIMATED" in [w["code"] for w in saved["warnings"]]

    async def test_daytime_is_untouched(self, client: httpx.AsyncClient) -> None:
        resp = await client.post("/v1/courses/generate", json={**GENERATE_BODY, "alternatives": 0})
        course = resp.json()["courses"][0]
        assert "NIGHT_HOURS_ESTIMATED" not in [w["code"] for w in course["warnings"]]
        # "night" sent by hand is ignored in the daytime
        forced = await client.post(
            "/v1/courses/generate", json={**GENERATE_BODY, "alternatives": 0, "conditions": ["night"]}
        )
        assert [s["place"]["id"] for s in forced.json()["courses"][0]["stops"]] == [
            s["place"]["id"] for s in course["stops"]
        ]
