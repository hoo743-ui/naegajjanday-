"""Outbox → Elasticsearch sync. The SQL database is canonical; this worker drains `search_outbox`."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.infra.db.base import utcnow
from app.infra.db.models import Place, SearchOutbox
from app.infra.search.client import PlaceSearch

MAX_ATTEMPTS = 5


def place_document(place: Place) -> dict[str, Any]:
    stats = place.stats
    return {
        "public_id": place.public_id,
        "name": place.name,
        "address": place.road_address or place.address,
        "category_code": place.category.code,
        "course_role": place.category.course_role,
        "tags": [pt.tag.name for pt in place.place_tags],
        "region_slug": place.region.slug,
        "location": {"lat": place.lat, "lon": place.lng},
        "price_per_person": place.price_per_person,
        "is_free": place.is_free,
        "bayes_rating": stats.bayes_rating if stats else None,
        "sentiment_score": stats.sentiment_score if stats else None,
        "popularity": stats.popularity if stats else 0.0,
        "status": place.status,
    }


async def drain_outbox(session: AsyncSession, search: PlaceSearch, batch_size: int = 500) -> dict[str, int]:
    rows = (
        await session.scalars(
            select(SearchOutbox)
            .where(SearchOutbox.processed_at.is_(None), SearchOutbox.attempts < MAX_ATTEMPTS)
            .order_by(SearchOutbox.id)
            .limit(batch_size)
        )
    ).all()
    if not rows:
        return {"processed": 0, "failed": 0}
    latest = {r.entity_id: r for r in rows if r.entity == "place"}  # last write wins per place
    places = (
        await session.scalars(
            select(Place)
            .where(Place.id.in_(latest))
            .options(
                selectinload(Place.category),
                selectinload(Place.region),
                selectinload(Place.stats),
                selectinload(Place.place_tags),
            )
        )
    ).all()
    by_id = {p.id: p for p in places}
    operations: list[dict[str, Any]] = []
    for entity_id, row in latest.items():
        place = by_id.get(entity_id)
        if row.op == "delete" or place is None:
            operations.append({"delete": {"_id": str(entity_id)}})
        else:
            operations.append({"index": {"_id": str(entity_id)}})
            operations.append(place_document(place))
    failed = 0
    try:
        resp = await search.bulk(operations)
        errors = {
            int(next(iter(item.values()))["_id"]): str(next(iter(item.values())).get("error"))
            for item in resp.get("items", [])
            if next(iter(item.values())).get("error") and next(iter(item.values())).get("status") != 404
        }
    except Exception as exc:  # cluster unreachable: keep rows for the next run
        errors = {entity_id: str(exc) for entity_id in latest}
    now = utcnow()
    for row in rows:
        row.attempts += 1
        if row.entity_id in errors:
            row.last_error = errors[row.entity_id][:500]
            failed += 1
        else:
            row.processed_at = now
    await session.commit()
    return {"processed": len(rows) - failed, "failed": failed}
