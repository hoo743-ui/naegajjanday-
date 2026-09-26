"""처음 오는 사람 · 자주 오는 사람 (docs/59 #1): asked for, read off a signed-in user's past, the places of
their past courses left out, and the setting echoed so 다시 짜기 keeps it."""

from __future__ import annotations

from datetime import timedelta

import httpx
from sqlalchemy import select, update

from app.core.deps import Container
from app.infra.db.base import utcnow
from app.infra.db.models import RecommendationLog, User
from tests.conftest import GENERATE_BODY, _token
from tests.integration.test_courses import generate


def ids(course: dict) -> set[str]:
    return {s["place"]["id"] for s in course["stops"]}


async def detail(client: httpx.AsyncClient, course: dict, headers: dict[str, str] | None = None) -> dict:
    resp = await client.get(f"/v1/courses/{course['id']}", headers=headers or {})
    assert resp.status_code == 200, resp.text
    return resp.json()["request"]


async def backdate_logs(container: Container, email: str, days: int) -> None:
    """Their courses so far were planned `days` ago — another day out in the same neighbourhood."""
    async with container.db.sessionmaker() as session:
        user_id = await session.scalar(select(User.id).where(User.email == email))
        await session.execute(
            update(RecommendationLog)
            .where(RecommendationLog.user_id == user_id)
            .values(created_at=utcnow() - timedelta(days=days))
        )
        await session.commit()


class TestAsked:
    async def test_default_is_a_first_visit(self, client: httpx.AsyncClient) -> None:
        course = (await generate(client, alternatives=0)).json()["courses"][0]
        echo = await detail(client, course)
        assert echo["familiarity"] == "first" and echo["familiarity_source"] is None

    async def test_regular_is_echoed_and_sent_back_by_a_reroll(self, client: httpx.AsyncClient) -> None:
        first = (await generate(client, alternatives=0)).json()["courses"][0]
        # 자주 오는 동네예요 → 안 가 본 곳으로 다시 짜기: the web sends the course just seen as excluded
        resp = await generate(
            client,
            alternatives=0,
            familiarity="regular",
            preferences={"exclude_place_ids": sorted(ids(first))},
        )
        assert resp.status_code == 200, resp.text
        regular = resp.json()["courses"][0]
        assert not ids(first) & ids(regular)
        echo = await detail(client, regular)
        assert echo["familiarity"] == "regular" and echo["familiarity_source"] == "asked"
        # 다시 짜기 sends the echo back as it is: still regular
        again = await generate(client, alternatives=0, familiarity=echo["familiarity"])
        assert again.status_code == 200, again.text
        assert (await detail(client, again.json()["courses"][0]))["familiarity"] == "regular"

    async def test_unknown_value_is_refused(self, client: httpx.AsyncClient) -> None:
        assert (await generate(client, familiarity="sometimes")).status_code == 422


class TestInferred:
    EMAIL = "regular@example.com"

    async def test_two_days_here_make_a_regular_and_their_places_are_left_out(
        self, client: httpx.AsyncClient, container: Container
    ) -> None:
        headers = await _token(container, self.EMAIL, "user")
        one = (
            await client.post(
                "/v1/courses/generate",
                json={**_body(), "start_at": "2026-09-20T18:00:00+09:00"},
                headers=headers,
            )
        ).json()["courses"][0]
        assert (await detail(client, one, headers))["familiarity"] == "first"
        await backdate_logs(container, self.EMAIL, days=10)

        # a second time, today: only one earlier day → still a first visit
        two = (
            await client.post(
                "/v1/courses/generate",
                json={**_body(), "start_at": "2026-09-20T18:10:00+09:00"},
                headers=headers,
            )
        ).json()["courses"][0]
        assert (await detail(client, two, headers))["familiarity"] == "first"

        # a third: planned here on two different days now → a regular, and nowhere they were shown before
        resp = await client.post(
            "/v1/courses/generate",
            json={**_body(), "start_at": "2026-09-20T18:20:00+09:00"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        three = resp.json()["courses"][0]
        echo = await detail(client, three, headers)
        assert echo["familiarity"] == "regular" and echo["familiarity_source"] == "history"
        assert not (ids(one) | ids(two)) & ids(three)

        # 처음처럼 대표 코스로: asked for, it wins over their history
        back = await client.post(
            "/v1/courses/generate",
            json={**_body(), "start_at": "2026-09-20T18:30:00+09:00", "familiarity": "first"},
            headers=headers,
        )
        assert back.status_code == 200, back.text
        echo = await detail(client, back.json()["courses"][0], headers)
        assert echo["familiarity"] == "first" and echo["familiarity_source"] == "asked"

    async def test_rerolls_on_one_day_are_one_visit(
        self, client: httpx.AsyncClient, container: Container
    ) -> None:
        headers = await _token(container, "sameday@example.com", "user")
        seen = []
        for minute in ("00", "10", "20"):
            resp = await client.post(
                "/v1/courses/generate",
                json={**_body(), "start_at": f"2026-09-20T18:{minute}:00+09:00"},
                headers=headers,
            )
            assert resp.status_code == 200, resp.text
            seen.append((await detail(client, resp.json()["courses"][0], headers))["familiarity"])
        assert seen == ["first", "first", "first"]


def _body() -> dict:
    return {**GENERATE_BODY, "alternatives": 0}
