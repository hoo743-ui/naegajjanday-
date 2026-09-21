"""`GET /v1/stays`: lodging rows go in through the real mapping + bulk writer, then come back out of the API.
Made-up names and a made-up spot far from every seeded region, removed again at the end."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest_asyncio
from sqlalchemy import delete, select

from app.core.deps import Container
from app.infra.db.models import Place, PlaceSource, PlaceStats, Region
from app.infra.ingestion.bulk import tourapi_stay
from app.infra.ingestion.bulk.common import BulkReport
from app.infra.ingestion.bulk.writer import BulkWriter

LAT, LNG = 36.0, 128.0
PHOTO = "http://tong.visitkorea.or.kr/cms/resource/9/room.jpg"
SLUG = "stay-test-zone"


class _OneRegion:
    def __init__(self, region_id: int) -> None:
        self._id = region_id

    def locate(self, lat: float, lng: float, sido: str | None = None, sigungu: str | None = None) -> int:
        return self._id


def _row(cid: str, title: str, code: str, dlat: float, photo: bool) -> dict[str, object]:
    return {
        "contentid": cid,
        "title": title,
        "lclsSystm3": code,
        "cat3": "",
        "mapx": str(LNG),
        "mapy": str(LAT + dlat),
        "addr1": "Mado Basa-gu Ajaro 1",
        "addr2": "",
        "tel": "",
        "firstimage": PHOTO if photo else "",
        "firstimage2": "",
    }


ROWS = [
    _row("s-1", "Gana Motel", "AC040100", 0.0010, False),  # ≈ 110 m, no photo
    _row("s-2", "Dara Hotel", "AC010100", 0.0100, True),  # ≈ 1.1 km, photo
    _row("s-3", "Mabasa Hanok", "AC030200", 0.0050, True),  # ≈ 560 m, photo
    _row("s-4", "Faraway Resort", "VE050200", 0.0900, True),  # ≈ 10 km
    _row("s-5", "Gana Campsite", "AC050100", 0.0010, True),  # not lodging → never written
]


@pytest_asyncio.fixture
async def lodging(container: Container) -> AsyncIterator[None]:
    async with container.db.sessionmaker() as session:
        region = Region(
            slug=SLUG,
            name="Stay Test Zone",
            level=3,
            center_lat=LAT,
            center_lng=LNG,
            radius_m=1200,
            status="draft",
            search_keywords=[],
        )
        session.add(region)
        await session.commit()
        region_id = region.id
        writer = BulkWriter(session, tourapi_stay.PROVIDER, _OneRegion(region_id))  # type: ignore[arg-type]
        await writer.prepare()
        report = await writer.write_all(
            list(tourapi_stay.iter_stays(ROWS, tourapi_stay.load_rules(), {}, BulkReport()))
        )
        assert report.created == 4
    yield
    async with container.db.sessionmaker() as session:
        ids = (await session.scalars(select(Place.id).where(Place.region_id == region_id))).all()
        await session.execute(delete(PlaceSource).where(PlaceSource.place_id.in_(ids)))
        await session.execute(delete(PlaceStats).where(PlaceStats.place_id.in_(ids)))
        await session.execute(delete(Place).where(Place.id.in_(ids)))
        await session.execute(delete(Region).where(Region.id == region_id))
        await session.commit()


class TestStays:
    async def test_photo_first_then_nearest_and_no_price(
        self, client: httpx.AsyncClient, lodging: None
    ) -> None:
        resp = await client.get("/v1/stays", params={"lat": LAT, "lng": LNG})
        body = resp.json()
        assert resp.status_code == 200 and body["radius_m"] == 3000
        assert [i["name"] for i in body["items"]] == ["Mabasa Hanok", "Dara Hotel", "Gana Motel"]
        first, last = body["items"][0], body["items"][-1]
        assert first["category"] == "stay.hanok" and first["category_label"]
        assert (
            first["thumbnail_url"] == PHOTO.replace("http://", "https://") and first["photo_credit"] is True
        )
        assert 500 < first["distance_m"] < 620 and len(first["id"]) >= 32
        assert last["thumbnail_url"] is None and last["photo_credit"] is False
        assert body["has_price"] is False and "예약처" in body["price_note"] and "공식" in body["price_note"]
        assert all("price" not in key for item in body["items"] for key in item)

    async def test_radius_and_limit(self, client: httpx.AsyncClient, lodging: None) -> None:
        wide = await client.get("/v1/stays", params={"lat": LAT, "lng": LNG, "radius_m": 15000})
        assert [i["name"] for i in wide.json()["items"]][-2:] == ["Faraway Resort", "Gana Motel"]
        one = await client.get("/v1/stays", params={"lat": LAT, "lng": LNG, "radius_m": 15000, "limit": 1})
        assert [i["name"] for i in one.json()["items"]] == ["Mabasa Hanok"]
        tight = await client.get("/v1/stays", params={"lat": LAT, "lng": LNG, "radius_m": 200})
        assert [i["name"] for i in tight.json()["items"]] == ["Gana Motel"]

    async def test_lodging_is_never_a_course_stop_or_a_sight(
        self, client: httpx.AsyncClient, lodging: None
    ) -> None:
        sights = (await client.get("/v1/attractions")).json()["items"]
        assert not [i for i in sights if i["category"].startswith("stay")]
        empty = await client.get("/v1/stays", params={"lat": 33.0, "lng": 126.0})
        assert empty.status_code == 200 and empty.json()["items"] == []

    async def test_bad_query_is_a_problem(self, client: httpx.AsyncClient) -> None:
        assert (await client.get("/v1/stays", params={"lat": 36.0})).status_code == 422
        resp = await client.get("/v1/stays", params={"lat": LAT, "lng": LNG, "radius_m": 50})
        assert resp.status_code == 422
