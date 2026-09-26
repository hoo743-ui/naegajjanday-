"""v2 engine, reason codes and the preference layer through the API (docs/29, docs/30)."""

from __future__ import annotations

from tests.conftest import GENERATE_BODY, BrowserLikeClient

KNOWN_REASONS = {
    "PURPOSE_MATCH",
    "LOCAL_SIGNIFICANCE",
    "NEWLY_OPENED",
    "WORTH_THE_TRIP",
    "UNIQUE_EXPERIENCE",
    "USER_PREFERENCE",
    "HIGH_PLACE_QUALITY",
    "BUDGET_FIT",
    "DIVERSITY",
    "ROUTE_BALANCE",
}


async def test_every_stop_says_why(client: BrowserLikeClient) -> None:
    body = (await client.post("/v1/courses/generate", json=GENERATE_BODY)).json()
    assert body["meta"]["algorithm"] == "v2"
    for course in body["courses"]:
        for stop in course["stops"]:
            assert set(stop["reason_codes"]) <= KNOWN_REASONS
    # and the reasons survive a reload
    course = body["courses"][0]
    again = (await client.get(f"/v1/courses/{course['id']}")).json()
    assert [s["reason_codes"] for s in again["course"]["stops"]] == [
        s["reason_codes"] for s in course["stops"]
    ]


async def test_v1_is_still_there_to_compare(client: BrowserLikeClient) -> None:
    body = (await client.post("/v1/courses/generate", json={**GENERATE_BODY, "algorithm": "v1"})).json()
    assert body["meta"]["algorithm"] == "v1"
    assert body["courses"]


async def test_the_three_answers_alone_make_a_course(client: BrowserLikeClient) -> None:
    res = await client.post(
        "/v1/courses/generate",
        json={**GENERATE_BODY, "pace": ["relaxed"], "move_style": "explorer", "wishes": ["night"]},
    )
    assert res.status_code == 200
    course = res.json()["courses"][0]
    assert course["stops"]
    assert course["totals"]["price"] <= GENERATE_BODY["budget_total"]  # a preference never breaks the budget


async def test_conflicting_answers_are_read_not_refused(client: BrowserLikeClient) -> None:
    res = await client.post(
        "/v1/courses/generate",
        json={
            **GENERATE_BODY,
            "pace": ["relaxed", "packed"],
            "move_style": "local",
            "wishes": ["romantic", "value"],
            "preferences": {"liked_tags": ["활기찬"], "disliked_tags": ["감성적인"], "exclude_place_ids": []},
        },
    )
    assert res.status_code == 200


async def test_interpret_says_it_back_in_words(client: BrowserLikeClient) -> None:
    res = await client.post(
        "/v1/courses/interpret",
        json={
            "pace": ["relaxed"],
            "move_style": "balanced",
            "wishes": ["night"],
            "budget_total": 80000,
            "party_size": 2,
        },
    )
    assert res.status_code == 200
    texts = [line["text"] for line in res.json()["summary"]]
    assert texts[:3] == ["여유로운 하루", "적당히 이동", "야경 포함"]
    assert texts[-1].startswith("80,000원")


async def test_unknown_answers_are_rejected(client: BrowserLikeClient) -> None:
    res = await client.post("/v1/courses/interpret", json={"pace": ["sleepy"]})
    assert res.status_code == 422
