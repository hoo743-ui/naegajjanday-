"""동 단위 지역 (level 4): listed when a district is opened or a name is searched, and a course can be planned in one."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest_asyncio
from sqlalchemy import delete, select, update

from app.core.deps import Container
from app.infra.db.models import Course, RecommendationLog, Region, RegionStat

DONG = "seoul-mapo-dtest01"


@pytest_asyncio.fixture
async def dong(container: Container) -> AsyncIterator[str]:
    """A neighbourhood drawn over the seeded hotspot: it owns no places, `region_stat` counts them."""
    async with container.db.sessionmaker() as session:
        hotspot = await session.scalar(select(Region).where(Region.slug == "seoul-hongdae"))
        assert hotspot is not None and hotspot.parent_id is not None
        region = Region(
            parent_id=hotspot.parent_id, slug=DONG, name="시험동", level=4, status="active",
            center_lat=hotspot.center_lat, center_lng=hotspot.center_lng, radius_m=900,
        )  # fmt: skip
        session.add(region)
        await session.flush()
        session.add(RegionStat(region_id=region.id, place_count=321))
        await session.commit()
    await container.cache.delete_prefix("")
    yield DONG
    async with container.db.sessionmaker() as session:
        region_id = await session.scalar(select(Region.id).where(Region.slug == DONG))
        for model in (Course, RecommendationLog):  # what was planned in it points at it
            await session.execute(update(model).where(model.region_id == region_id).values(region_id=None))
        await session.execute(delete(Region).where(Region.id == region_id))
        await session.commit()


class TestDongRegions:
    async def test_not_in_the_whole_list_but_under_its_district_and_in_search(
        self, client: httpx.AsyncClient, dong: str
    ) -> None:
        everything = (await client.get("/v1/meta/regions")).json()["items"]
        assert everything and all(r["level"] < 4 for r in everything)
        province = (await client.get("/v1/meta/regions", params={"parent": "seoul"})).json()["items"]
        assert all(r["level"] < 4 for r in province)

        district = (await client.get("/v1/meta/regions", params={"parent": "seoul-mapo"})).json()["items"]
        mine = next(r for r in district if r["slug"] == dong)
        assert mine["level"] == 4 and mine["place_count"] == 321 and mine["parent"]["slug"] == "seoul-mapo"
        assert any(r["level"] == 3 for r in district)  # the hotspots of the district are still there

        found = (await client.get("/v1/meta/regions", params={"q": "시험동"})).json()["items"]
        assert [r["slug"] for r in found] == [dong]

    async def test_a_course_is_planned_inside_it(self, client: httpx.AsyncClient, dong: str) -> None:
        resp = await client.post(
            "/v1/courses/generate",
            json={
                "region": dong, "purpose": "date", "budget_total": 80000, "party_size": 2,
                "start_at": "2026-10-10T13:00:00+09:00", "duration_min": 240, "transport": "walk",
                "alternatives": 0,
            },
        )  # fmt: skip
        assert resp.status_code == 200, resp.text
        course = resp.json()["courses"][0]
        assert len(course["stops"]) >= 2
        saved = (await client.get(f"/v1/courses/{course['id']}")).json()
        assert saved["request"]["region"]["slug"] == dong
        hot = (await client.get(f"/v1/meta/regions/{dong}/hot")).json()
        assert hot["region"] == "시험동" and hot["scope"]  # around its circle, else its district: never a 404
