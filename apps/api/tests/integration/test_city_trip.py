"""A whole city as the destination goes where people really go, not around the city's centre point."""

from __future__ import annotations

import httpx
from sqlalchemy import select, update

from app.core.deps import Container
from app.infra.db.models import Category, Place, PlaceStats
from tests.conftest import GENERATE_BODY


async def make_popular(container: Container, region_slug_prefix: str) -> list[str]:
    """Gives the sights of the seeded neighbourhoods a measured rank, as `visit_hubs load` would."""
    async with container.db.sessionmaker() as session:
        rows = (
            await session.execute(
                select(Place.id, Place.public_id)
                .join(Category, Category.id == Place.category_id)
                .where(
                    Category.course_role.in_(["ATTRACTION", "NIGHTVIEW", "CULTURE"]),
                    Place.status == "approved",
                )
            )
        ).all()
        ids = [pid for pid, _ in rows]
        await session.execute(update(PlaceStats).where(PlaceStats.place_id.in_(ids)).values(popularity=0.9))
        await session.commit()
        return [public_id for _, public_id in rows]


class TestCityTrip:
    async def test_a_city_without_visit_data_is_planned_as_before(self, client: httpx.AsyncClient) -> None:
        resp = await client.post(
            "/v1/courses/generate", json={**GENERATE_BODY, "region": "seoul", "alternatives": 0}
        )
        assert resp.status_code == 200, resp.text
        echo = (await client.get(f"/v1/courses/{resp.json()['courses'][0]['id']}")).json()["request"]
        assert echo["city"] is None

    async def test_a_city_trip_visits_a_well_visited_sight_every_day(
        self, client: httpx.AsyncClient, container: Container
    ) -> None:
        sights = await make_popular(container, "seoul")
        try:
            resp = await client.post(
                "/v1/courses/generate",
                json={**GENERATE_BODY, "region": "seoul", "purpose": "travel", "nights": 1, "budget_total": 240000,
                      "start_at": "2026-09-22T11:00:00+09:00", "transport": "transit"},
            )  # fmt: skip
            assert resp.status_code == 200, resp.text
            days = resp.json()["courses"]
            assert [c["label"] for c in days] == ["1일차", "2일차"]
            for day in days:
                in_course = {s["place"]["id"] for s in day["stops"]}
                assert in_course & set(sights)  # the area's own sight is in it
            visited = [s["place"]["id"] for c in days for s in c["stops"]]
            assert len(visited) == len(set(visited))
            echo = (await client.get(f"/v1/courses/{days[0]['id']}")).json()["request"]
            assert echo["city"] == {"slug": "seoul", "name": echo["city"]["name"]}
            assert echo["regions"] or echo["origin_label"]  # the areas are what the page names
        finally:
            async with container.db.sessionmaker() as session:  # the database is shared by the whole session
                await session.execute(update(PlaceStats).values(popularity=0.0))
                await session.commit()
