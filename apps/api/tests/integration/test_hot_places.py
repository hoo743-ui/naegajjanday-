"""'이 지역 핫플': where people really go around here, for someone who does not know the area."""

from __future__ import annotations

import httpx
from sqlalchemy import select, update

from app.core.deps import Container
from app.infra.db.models import Category, Place, PlaceStats, Region


async def rank_the_sights(container: Container, region_slug: str, popularity: float) -> int:
    async with container.db.sessionmaker() as session:
        region_id = await session.scalar(select(Region.id).where(Region.slug == region_slug))
        ids = (
            await session.scalars(
                select(Place.id)
                .join(Category, Category.id == Place.category_id)
                .where(Place.region_id == region_id, Category.course_role.in_(["ATTRACTION", "CULTURE"]))
            )
        ).all()
        await session.execute(
            update(PlaceStats).where(PlaceStats.place_id.in_(ids)).values(popularity=popularity)
        )
        await session.commit()
        return len(ids)


class TestHotPlaces:
    async def test_nothing_measured_means_nothing_claimed(self, client: httpx.AsyncClient) -> None:
        body = (await client.get("/v1/meta/regions/seoul-hongdae/hot")).json()
        assert body["items"] == [] and body["source"]
        assert (await client.get("/v1/meta/regions/atlantis/hot")).status_code == 404

    async def test_the_most_visited_come_first_with_their_rank(
        self, client: httpx.AsyncClient, container: Container
    ) -> None:
        ranked = await rank_the_sights(container, "seoul-hongdae", 0.96)
        try:
            body = (await client.get("/v1/meta/regions/seoul-hongdae/hot", params={"limit": 5})).json()
            assert 0 < len(body["items"]) <= min(5, ranked)
            assert {i["rank"] for i in body["items"]} == {5}  # popularity 0.96 = 5th in its district
            assert all(i["id"] and i["name"] and i["category_name"] for i in body["items"])
            # a district with nothing of its own is answered through what lies under it
            district = (await client.get("/v1/meta/regions/seoul-mapo/hot")).json()
            assert district["items"] and district["scope"] == district["region"]
        finally:
            await rank_the_sights(container, "seoul-hongdae", 0.0)
