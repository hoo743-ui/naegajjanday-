"""믿을 이유 한 줄 (docs/59 #15) through the API: read off the stored rows of each stop, nothing without them."""

from __future__ import annotations

from datetime import date

import httpx
from sqlalchemy import select

from app.core.deps import Container
from app.infra.db.base import utcnow
from app.infra.db.models import MenuItem, Place, PlaceSource
from tests.integration.test_courses import generate


async def test_a_stop_says_its_licence_year_and_menu_price(
    client: httpx.AsyncClient, container: Container
) -> None:
    course = (await generate(client, alternatives=0)).json()["courses"][0]
    assert all("trust" in s for s in course["stops"])
    stop = next(s for s in course["stops"] if s["place"]["kind"] == "place")
    since = date.today().year - 1990
    async with container.db.sessionmaker() as session:
        place_id = await session.scalar(select(Place.id).where(Place.public_id == stop["place"]["id"]))
        assert place_id is not None
        session.add(
            PlaceSource(
                place_id=place_id,
                provider="lic_restaurant",
                external_id=f"trust-test-{place_id}",
                raw={"인허가일자": "1990-04-01"},
                fetched_at=utcnow(),
                content_hash="x" * 64,
            )
        )
        session.add(
            MenuItem(place_id=place_id, name="칼국수", price=9000, is_signature=True, source="goodprice")
        )
        await session.commit()

    detail = (await client.get(f"/v1/courses/{course['id']}")).json()["course"]
    again = next(s for s in detail["stops"] if s["place"]["id"] == stop["place"]["id"])
    trust = again["trust"]
    assert trust is not None
    assert trust["text"] == f"1990년부터 {since}년째 영업 · 칼국수 9,000원"
    assert trust["kind"] == "long_run" and trust["source"] == "지자체 인허가(영업 신고) 기록"
    kinds = [f["kind"] for f in trust["facts"]]
    assert kinds[:2] == ["long_run", "menu_price"]
    assert trust["facts"][1]["source"] == "행정안전부 착한가격업소 조사 가격"
    # every other stop: a line from its own rows, or nothing — never filler
    for s in detail["stops"]:
        assert s["trust"] is None or 0 < len(s["trust"]["text"]) <= 40
        if s["trust"]:
            assert "인기" not in s["trust"]["text"] and "맛집" not in s["trust"]["text"]
