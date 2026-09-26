from __future__ import annotations

from datetime import datetime

import httpx

from tests.conftest import GENERATE_BODY

PROBLEM = "application/problem+json"


async def generate(client: httpx.AsyncClient, **overrides: object) -> httpx.Response:
    return await client.post("/v1/courses/generate", json={**GENERATE_BODY, **overrides})


class TestGenerate:
    async def test_hongdae_date_for_two_with_40000(self, client: httpx.AsyncClient) -> None:
        resp = await generate(client)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["meta"]["scoring_profile"].startswith("date@v")  # version is bumped by admin edits
        assert body["meta"]["template"] == "date-evening"
        assert body["meta"]["candidates"] > 0 and body["request_id"]

        course = body["courses"][0]
        assert course["label"] == "추천 코스"
        roles = [s["role"] for s in course["stops"]]
        assert roles == ["MEAL", "CAFE", "ATTRACTION"]  # BAR (optional) is dropped at 20,000/person
        assert [s["position"] for s in course["stops"]] == [1, 2, 3]

        totals = course["totals"]
        assert totals["price"] == sum(s["est_price"] for s in course["stops"])
        assert totals["budget_left"] == 40000 - totals["price"]
        assert totals["price_per_person"] * 2 == totals["price"]
        assert totals["price"] <= 40000
        assert totals["budget_utilization"] == round(totals["price"] / 40000, 3)
        assert totals["travel_min"] == sum(s["from_prev"]["travel_min"] for s in course["stops"])
        assert totals["distance_m"] == sum(s["from_prev"]["distance_m"] for s in course["stops"])

        times = [
            (datetime.fromisoformat(s["arrive_at"]), datetime.fromisoformat(s["leave_at"]))
            for s in course["stops"]
        ]
        assert times[0][0].utcoffset().total_seconds() == 9 * 3600  # type: ignore[union-attr]
        assert times[0][0] >= datetime.fromisoformat(GENERATE_BODY["start_at"])  # type: ignore[arg-type]
        assert all(a < b for a, b in times) and all(times[i][1] <= times[i + 1][0] for i in range(2))

        for stop in course["stops"]:
            assert set(stop["score_breakdown"]) == {
                "budget", "distance", "rating", "sentiment", "congestion", "time_fit", "preference", "purpose_fit",
                "buzz",
                "curated",
            }  # fmt: skip
            assert all(0 <= v <= 1 for v in stop["score_breakdown"].values())
            assert stop["reason"] and stop["from_prev"]["mode"] == "walk"
            assert stop["est_price"] == (stop["place"]["price_per_person"] or 0) * 2
        assert (
            course["summary"] and course["route"]["polyline"] and course["route"]["optimizer"] == "held_karp"
        )
        categories = [s["place"]["category"] for s in course["stops"]]
        assert len(set(categories)) == len(categories)

    async def test_alternatives_differ_and_are_labeled(self, client: httpx.AsyncClient) -> None:
        courses = (await generate(client)).json()["courses"]
        assert len(courses) == 3
        place_sets = [frozenset(s["place"]["id"] for s in c["stops"]) for c in courses]
        assert len(set(place_sets)) == 3
        for other in place_sets[1:]:
            assert len(place_sets[0] & other) / max(len(place_sets[0]), len(other)) < 0.5
        assert len({c["label"] for c in courses}) == 3 and len({c["id"] for c in courses}) == 3

    async def test_budget_too_low_problem(self, client: httpx.AsyncClient) -> None:
        resp = await generate(client, budget_total=6000)
        assert resp.status_code == 422
        assert resp.headers["content-type"].startswith(PROBLEM)
        problem = resp.json()
        assert problem["code"] == "BUDGET_TOO_LOW" and problem["status"] == 422
        assert problem["type"].endswith("/errors/budget-too-low")
        assert problem["meta"]["min_budget"] == 16000
        assert "16,000원" in problem["detail"] and "홍대입구" in problem["detail"]
        assert problem["trace_id"] == resp.headers["x-request-id"]

    async def test_region_not_found_and_purpose_not_found(self, client: httpx.AsyncClient) -> None:
        resp = await generate(client, region="atlantis")
        assert (resp.status_code, resp.json()["code"]) == (404, "REGION_NOT_FOUND")
        resp = await generate(client, purpose="heist")
        assert (resp.status_code, resp.json()["code"]) == (404, "PURPOSE_NOT_FOUND")

    async def test_validation_problem(self, client: httpx.AsyncClient) -> None:
        resp = await client.post(
            "/v1/courses/generate", json={"purpose": "date", "party_size": 0, "budget_total": 1}
        )
        assert resp.status_code == 422 and resp.headers["content-type"].startswith(PROBLEM)
        assert resp.json()["code"] == "VALIDATION_ERROR" and resp.json()["errors"]

    async def test_origin_resolves_nearest_region(self, client: httpx.AsyncClient) -> None:
        resp = await generate(client, region=None, origin={"lat": 37.5446, "lng": 127.0559})
        assert resp.status_code == 200
        far = await generate(client, region=None, origin={"lat": 33.5, "lng": 126.5})
        assert far.json()["code"] == "REGION_NOT_FOUND"

    async def test_disliked_tag_and_excluded_place_are_honoured(self, client: httpx.AsyncClient) -> None:
        first = (await generate(client, alternatives=0)).json()["courses"][0]
        banned = first["stops"][0]["place"]["id"]
        prefs = {"liked_tags": ["조용한"], "disliked_tags": ["웨이팅"], "exclude_place_ids": [banned]}
        course = (await generate(client, alternatives=0, preferences=prefs)).json()["courses"][0]
        assert banned not in [s["place"]["id"] for s in course["stops"]]
        assert all("웨이팅" not in s["place"]["tags"] for s in course["stops"])

    async def test_several_purposes_blend_and_any_veto_holds(self, client: httpx.AsyncClient) -> None:
        # a date alone gets the evening bar; bring the family along and the bar is gone for everyone
        resp = await generate(client, budget_total=160000, alternatives=0, purposes=["family"])
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["meta"]["scoring_profile"].startswith("date+family@v")
        course = body["courses"][0]
        assert "BAR" not in [s["role"] for s in course["stops"]]
        detail = (await client.get(f"/v1/courses/{course['id']}")).json()
        assert [p["code"] for p in detail["request"]["purposes"]] == ["date", "family"]
        # asking for a drink does not override the veto either
        again = await generate(
            client, budget_total=160000, alternatives=0, purposes=["family"], extras=["BAR"]
        )
        assert "BAR" not in [s["role"] for s in again.json()["courses"][0]["stops"]]
        unknown = await generate(client, purposes=["nope"])
        assert unknown.status_code == 404

    async def test_a_day_across_two_neighbourhoods(self, client: httpx.AsyncClient) -> None:
        resp = await generate(
            client, regions=["seoul-hongdae", "seoul-seongsu"], budget_total=120000, alternatives=2,
            start_at="2026-09-22T12:00:00+09:00", duration_min=420,
        )  # fmt: skip
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["courses"]) == 1  # one joined course; alternatives are per neighbourhood, not per day
        course = body["courses"][0]
        assert course["totals"]["price"] <= 120000
        assert course["totals"]["price"] == sum(s["est_price"] for s in course["stops"])
        hops = [s for s in course["stops"] if s["from_prev"].get("hop_to")]
        assert len(hops) == 1 and hops[0]["from_prev"]["mode"] in ("transit", "car")
        assert hops[0]["position"] > 1
        times = [s["arrive_at"] for s in course["stops"]]
        assert times == sorted(times)  # the second neighbourhood starts after the first one ends
        ids = [s["place"]["id"] for s in course["stops"]]
        assert len(ids) == len(set(ids))
        detail = (await client.get(f"/v1/courses/{course['id']}")).json()
        assert [r["slug"] for r in detail["request"]["regions"]] == ["seoul-hongdae", "seoul-seongsu"]
        missing = await generate(client, regions=["seoul-hongdae", "atlantis"])
        assert missing.status_code == 404

    async def test_a_trip_of_two_days_splits_the_budget_and_never_repeats_a_place(
        self, client: httpx.AsyncClient
    ) -> None:
        resp = await generate(
            client, nights=1, budget_total=200000, start_at="2026-09-22T14:00:00+09:00", alternatives=2
        )
        assert resp.status_code == 200, resp.text
        courses = resp.json()["courses"]
        assert [c["label"] for c in courses] == ["1일차", "2일차"]
        assert sum(c["totals"]["price"] for c in courses) <= 200000
        ids = [s["place"]["id"] for c in courses for s in c["stops"]]
        assert len(ids) == len(set(ids))  # day two never goes back to a place from day one
        first, second = [(await client.get(f"/v1/courses/{c['id']}")).json() for c in courses]
        assert (first["request"]["day"], first["request"]["days"]) == (1, 2)
        assert second["request"]["trip_budget_total"] == 200000
        # each day answers to its own share, and what day one left over went to day two
        assert first["request"]["budget_total"] + second["request"]["budget_total"] >= 200000 - 2000
        assert second["request"]["budget_total"] >= 200000 - first["request"]["budget_total"] - 1000
        assert second["request"]["start_at"].startswith("2026-09-23T10:00")
        assert [s["label"] for s in first["siblings"]] == ["1일차", "2일차"]  # the days are the tabs

    async def test_a_rainy_day_keeps_the_course_indoors(self, client: httpx.AsyncClient) -> None:
        dry = (await generate(client, alternatives=0)).json()["courses"][0]
        wet_resp = await generate(client, alternatives=0, conditions=["rain", "nonsense"])
        assert wet_resp.status_code == 200, wet_resp.text
        wet = wet_resp.json()["courses"][0]
        assert "ATTRACTION" in [s["role"] for s in dry["stops"]]  # the usual evening has a walk in it
        assert "ATTRACTION" not in [
            s["role"] for s in wet["stops"]
        ]  # in the rain the walk becomes something indoors
        outdoors = [s["place"]["name"] for s in wet["stops"] if "야외" in s["place"]["tags"]]
        assert outdoors == []
        assert wet["totals"]["price"] <= 40000
        echo = (await client.get(f"/v1/courses/{wet['id']}")).json()["request"]
        assert echo["conditions"] == ["rain"]  # an unknown condition is dropped, not an error

    async def test_bigger_budget_keeps_the_bar_slot(self, client: httpx.AsyncClient) -> None:
        body = (await generate(client, budget_total=160000, alternatives=0)).json()
        course = body["courses"][0]
        # 80,000원/인이면 "넉넉한 저녁" 틀로 넘어간다: 예산이 들르는 곳의 수와 종류를 정한다
        assert body["meta"]["template"] == "date-evening-plenty"
        roles = [s["role"] for s in course["stops"]]
        assert roles[0] == "MEAL" and roles[-1] == "BAR" and len(roles) >= 4
        bar = course["stops"][-1]
        assert datetime.fromisoformat(bar["arrive_at"]).hour >= 17

    async def test_other_purposes_and_regions(self, client: httpx.AsyncClient) -> None:
        solo = await generate(client, region="seoul-seongsu", purpose="solo", party_size=1, budget_total=30000,
                              start_at="2026-09-22T12:00:00+09:00")  # fmt: skip
        assert solo.status_code == 200 and solo.json()["meta"]["template"] == "solo-lunch"
        trip = await generate(client, region="busan-seomyeon", purpose="travel", party_size=3, budget_total=240000,
                              start_at="2026-09-23T10:00:00+09:00", duration_min=540, transport="transit")  # fmt: skip
        # 80,000원/인 → 같은 여행 틀에 디저트·술 한잔이 더해진 "넉넉한 하루"
        assert trip.status_code == 200 and trip.json()["meta"]["template"] == "travel-fullday-plenty"
        assert len(trip.json()["courses"][0]["stops"]) >= 4

    async def test_idempotency_key_replays_the_same_response(self, client: httpx.AsyncClient) -> None:
        headers = {"Idempotency-Key": "abc-123"}
        a = await client.post("/v1/courses/generate", json=GENERATE_BODY, headers=headers)
        b = await client.post(
            "/v1/courses/generate", json={**GENERATE_BODY, "budget_total": 90000}, headers=headers
        )
        assert a.json()["request_id"] == b.json()["request_id"]


class TestFollowUps:
    async def test_get_shared_course_with_og(self, client: httpx.AsyncClient) -> None:
        course = (await generate(client)).json()["courses"][0]
        resp = await client.get(f"/v1/courses/{course['id']}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["course"]["totals"] == course["totals"]
        assert [s["place"]["id"] for s in body["course"]["stops"]] == [
            s["place"]["id"] for s in course["stops"]
        ]
        assert [s["arrive_at"] for s in body["course"]["stops"]] == [s["arrive_at"] for s in course["stops"]]
        # the web route is /course/{id} (singular) — a shared link must not 404
        assert body["og"]["url"] == f"http://localhost:3000/course/{course['id']}"
        assert "→" in body["og"]["description"]
        # nobody owns an anonymously generated course: anyone may edit it, nobody has saved it
        assert (body["is_owner"], body["can_edit"], body["is_saved"]) == (False, True, False)
        assert (await client.get("/v1/courses/nope")).json()["code"] == "COURSE_NOT_FOUND"

    async def test_detail_keeps_what_a_reload_and_a_reroll_need(self, client: httpx.AsyncClient) -> None:
        """새로고침·공유 링크는 GET 만 부른다: 근처 행사도, '다시 짜기'에 필요한 조건도 여기서 나와야 한다."""
        generated = (await generate(client)).json()
        assert generated["nearby_events"]  # the fixture has events running that day
        detail = (await client.get(f"/v1/courses/{generated['courses'][0]['id']}")).json()
        assert detail["nearby_events"] == generated["nearby_events"]
        echo = detail["request"]
        # planned from the region centre → no point to send back, the slug is enough
        assert echo["origin"] is None and echo["origin_label"] is None
        assert echo["preferences"] == {"liked_tags": [], "disliked_tags": []}

        point = {"lat": 37.5561, "lng": 126.9236}
        prefs = {"liked_tags": ["조용한"], "disliked_tags": ["웨이팅"], "exclude_place_ids": []}
        around = await generate(
            client, region=None, origin=point, origin_label="테스트역", preferences=prefs, alternatives=0
        )
        assert around.status_code == 200, around.text
        echo = (await client.get(f"/v1/courses/{around.json()['courses'][0]['id']}")).json()["request"]
        assert echo["origin"] == point and echo["origin_label"] == "테스트역"
        assert echo["region"]["slug"] == "seoul-hongdae"
        assert echo["preferences"] == {"liked_tags": ["조용한"], "disliked_tags": ["웨이팅"]}
        # the echo is a valid generate request again (region + origin together keep the same spot)
        again = await generate(
            client,
            region=echo["region"]["slug"],
            origin=echo["origin"],
            origin_label=echo["origin_label"],
            preferences=echo["preferences"],
            alternatives=0,
        )
        assert again.status_code == 200, again.text

    async def test_swap_replaces_only_that_stop(self, client: httpx.AsyncClient) -> None:
        course = (await generate(client, alternatives=0)).json()["courses"][0]
        resp = await client.post(
            f"/v1/courses/{course['id']}/swap", json={"position": 2, "strategy": "random_top"}
        )
        assert resp.status_code == 200, resp.text
        swapped = resp.json()
        before = [s["place"]["id"] for s in course["stops"]]
        after = [s["place"]["id"] for s in swapped["stops"]]
        assert after[0] == before[0] and after[2] == before[2] and after[1] != before[1]
        assert swapped["stops"][1]["role"] == "CAFE" and swapped["id"] == course["id"]
        assert swapped["totals"]["price"] == sum(s["est_price"] for s in swapped["stops"])
        assert swapped["totals"]["budget_left"] == 40000 - swapped["totals"]["price"]
        persisted = (await client.get(f"/v1/courses/{course['id']}")).json()["course"]
        assert [s["place"]["id"] for s in persisted["stops"]] == after

    async def test_swap_cheaper_and_invalid_position(self, client: httpx.AsyncClient) -> None:
        course = (await generate(client, alternatives=0)).json()["courses"][0]
        meal_price = course["stops"][0]["est_price"]
        resp = await client.post(
            f"/v1/courses/{course['id']}/swap", json={"position": 1, "strategy": "cheaper"}
        )
        assert resp.status_code == 200 and resp.json()["stops"][0]["est_price"] < meal_price
        free = await client.post(
            f"/v1/courses/{course['id']}/swap", json={"position": 3, "strategy": "cheaper"}
        )
        assert (free.status_code, free.json()["code"]) == (422, "SWAP_NOT_POSSIBLE")  # nothing beats free
        bad = await client.post(
            f"/v1/courses/{course['id']}/swap", json={"position": 9, "strategy": "closer"}
        )
        assert bad.status_code == 422

    async def test_reorder_recomputes_timeline(self, client: httpx.AsyncClient) -> None:
        course = (await generate(client, alternatives=0)).json()["courses"][0]
        resp = await client.post(f"/v1/courses/{course['id']}/reorder", json={"order": [2, 1, 3]})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert [s["place"]["id"] for s in body["stops"]] == [
            course["stops"][i]["place"]["id"] for i in (1, 0, 2)
        ]
        assert [s["position"] for s in body["stops"]] == [1, 2, 3]
        assert body["route"]["optimizer"] == "manual" and body["totals"]["price"] == course["totals"]["price"]
        bad = await client.post(f"/v1/courses/{course['id']}/reorder", json={"order": [1, 1, 3]})
        assert bad.status_code == 422

    async def test_remove_stop_keeps_the_rest_in_order(self, client: httpx.AsyncClient) -> None:
        course = (await generate(client, alternatives=0)).json()["courses"][0]
        assert len(course["stops"]) == 3
        resp = await client.delete(f"/v1/courses/{course['id']}/stops/2")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert [s["place"]["id"] for s in body["stops"]] == [
            course["stops"][i]["place"]["id"] for i in (0, 2)
        ]
        assert [s["position"] for s in body["stops"]] == [1, 2]
        assert body["totals"]["price"] == course["totals"]["price"] - course["stops"][1]["est_price"]
        # the course of record changed, not just this response
        again = (await client.get(f"/v1/courses/{course['id']}")).json()["course"]
        assert [s["place"]["id"] for s in again["stops"]] == [s["place"]["id"] for s in body["stops"]]
        # two places are the least a course keeps; a position that is not there is a clear no
        assert (await client.delete(f"/v1/courses/{course['id']}/stops/1")).status_code == 422
        assert (await client.delete(f"/v1/courses/{course['id']}/stops/9")).status_code == 422

    async def test_narrative_sse_uses_template_without_llm(self, client: httpx.AsyncClient) -> None:
        course = (await generate(client, alternatives=0)).json()["courses"][0]
        resp = await client.get(f"/v1/courses/{course['id']}/narrative")
        assert resp.status_code == 200 and resp.headers["content-type"].startswith("text/event-stream")
        assert "event: token" in resp.text and resp.text.rstrip().endswith("data: {}")
        assert "event: done" in resp.text and course["stops"][0]["reason"][:6] in resp.text

    async def test_save_list_feedback_delete(
        self, client: httpx.AsyncClient, user_headers: dict[str, str], admin_headers: dict[str, str]
    ) -> None:
        course = (await generate(client, alternatives=0)).json()["courses"][0]
        assert (await client.post(f"/v1/courses/{course['id']}/save")).status_code == 401
        saved = await client.post(f"/v1/courses/{course['id']}/save", headers=user_headers)
        assert saved.status_code == 200 and saved.json()["status"] == "saved"
        mine = (await client.get("/v1/me/courses", headers=user_headers)).json()
        item = next(c for c in mine["items"] if c["id"] == course["id"])
        # the /my card renders straight from the list item — no per-course detail fetch
        assert item["stop_names"] == [s["place"]["name"] for s in course["stops"]]
        assert item["duration_min"] == course["totals"]["duration_min"] > 0
        assert item["total_price"] == course["totals"]["price"] and item["status"] == "saved"
        assert item["region_name"] == "홍대입구" and item["purpose_name"] and item["party_size"] == 2
        # the detail answers for the VIEWER: a friend opening the shared link is not "saved / mine"
        url = f"/v1/courses/{course['id']}"
        as_owner = (await client.get(url, headers=user_headers)).json()
        assert (as_owner["is_owner"], as_owner["can_edit"], as_owner["is_saved"]) == (True, True, True)
        as_anon = (await client.get(url)).json()
        assert (as_anon["is_owner"], as_anon["can_edit"], as_anon["is_saved"]) == (False, False, False)
        assert as_anon["course"]["status"] == "saved"  # the raw status alone would have lied to them
        as_friend = (await client.get(url, headers=admin_headers)).json()
        assert (as_friend["is_owner"], as_friend["can_edit"], as_friend["is_saved"]) == (False, False, False)
        # once owned, anonymous callers can no longer modify it
        anon = await client.post(
            f"/v1/courses/{course['id']}/swap", json={"position": 2, "strategy": "closer"}
        )
        assert anon.status_code == 403
        fb = await client.post(
            f"/v1/courses/{course['id']}/feedback",
            headers=user_headers,
            json={
                "rating": 5,
                "visited": True,
                "actual_spend": 35000,
                "stop_feedback": [{"position": 1, "liked": True}],
            },
        )
        assert fb.status_code == 200
        prefs = (await client.get("/v1/me/preferences", headers=user_headers)).json()
        assert prefs["category_weights"][course["stops"][0]["place"]["category"]] == 0.2  # EMA alpha
        assert (
            await client.delete(f"/v1/me/courses/{course['id']}", headers=user_headers)
        ).status_code == 204
        assert (await client.get(f"/v1/courses/{course['id']}")).status_code == 404

    async def test_owned_but_unsaved_course_is_read_only_for_others(
        self, client: httpx.AsyncClient, user_headers: dict[str, str]
    ) -> None:
        created = await client.post(
            "/v1/courses/generate", json={**GENERATE_BODY, "alternatives": 0}, headers=user_headers
        )
        url = f"/v1/courses/{created.json()['courses'][0]['id']}"
        mine = (await client.get(url, headers=user_headers)).json()
        assert (mine["is_owner"], mine["can_edit"], mine["is_saved"]) == (True, True, False)
        theirs = (await client.get(url)).json()
        assert (theirs["is_owner"], theirs["can_edit"], theirs["is_saved"]) == (False, False, False)
        # `can_edit` mirrors the write endpoints exactly
        assert (await client.post(f"{url}/reorder", json={"order": [1, 2, 3]})).status_code == 403
        assert (await client.get(url, headers={"Authorization": "Bearer junk"})).status_code == 401


class TestRateLimit:
    async def test_anonymous_generate_is_limited_to_10_per_hour(self, client: httpx.AsyncClient) -> None:
        for i in range(10):
            ok = await generate(client, budget_total=40000 + i * 1000, alternatives=0)
            assert ok.status_code == 200
            assert ok.headers["x-ratelimit-limit"] == "10"
            assert ok.headers["x-ratelimit-remaining"] == str(9 - i)
        blocked = await generate(client, budget_total=70000)
        assert blocked.status_code == 429 and blocked.headers["content-type"].startswith(PROBLEM)
        assert blocked.json()["code"] == "RATE_LIMITED"
        assert int(blocked.headers["retry-after"]) > 0 and blocked.headers["x-ratelimit-remaining"] == "0"

    async def test_signed_in_users_get_the_higher_limit(
        self, client: httpx.AsyncClient, user_headers: dict[str, str]
    ) -> None:
        resp = await client.post("/v1/courses/generate", json=GENERATE_BODY, headers=user_headers)
        assert resp.status_code == 200 and resp.headers["x-ratelimit-limit"] == "60"
