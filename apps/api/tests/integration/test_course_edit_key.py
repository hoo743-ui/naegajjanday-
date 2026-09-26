"""Only the anonymous creator may edit an ownerless course (release audit P0, docs/28)."""

from __future__ import annotations

import httpx

from tests.conftest import GENERATE_BODY, BrowserLikeClient


async def test_a_stranger_with_the_link_cannot_change_the_course(client: BrowserLikeClient) -> None:
    gen = await client.post("/v1/courses/generate", json=GENERATE_BODY)
    body = gen.json()
    assert body["edit_key"]
    course = body["courses"][0]

    mine = (await client.get(f"/v1/courses/{course['id']}")).json()
    assert mine["can_edit"] is True

    keys = dict(client.course_keys)
    client.stranger()  # a friend opening the shared link
    theirs = (await client.get(f"/v1/courses/{course['id']}")).json()
    assert theirs["can_edit"] is False
    swap = await client.post(
        f"/v1/courses/{course['id']}/swap", json={"position": 1, "strategy": "random_top"}
    )
    assert swap.status_code == 403
    reorder = await client.post(f"/v1/courses/{course['id']}/reorder", json={"order": [2, 1, 3]})
    assert reorder.status_code == 403
    assert (await client.delete(f"/v1/courses/{course['id']}/stops/2")).status_code == 403
    wrong = await client.post(
        f"/v1/courses/{course['id']}/swap",
        json={"position": 1, "strategy": "random_top"},
        headers={"X-Course-Key": "not-the-key"},
    )
    assert wrong.status_code == 403

    client.course_keys.update(keys)  # back in the creator's browser
    assert (
        await client.post(f"/v1/courses/{course['id']}/reorder", json={"order": [2, 1, 3]})
    ).status_code == 200


async def test_two_anonymous_visitors_never_share_courses(client: httpx.AsyncClient) -> None:
    a = (await client.post("/v1/courses/generate", json=GENERATE_BODY)).json()
    b = (await client.post("/v1/courses/generate", json=GENERATE_BODY)).json()
    assert a["courses"][0]["id"] != b["courses"][0]["id"]
    assert a["edit_key"] != b["edit_key"]


async def test_signed_in_courses_carry_no_key(
    client: httpx.AsyncClient, user_headers: dict[str, str]
) -> None:
    body = (await client.post("/v1/courses/generate", json=GENERATE_BODY, headers=user_headers)).json()
    assert body["edit_key"] is None
