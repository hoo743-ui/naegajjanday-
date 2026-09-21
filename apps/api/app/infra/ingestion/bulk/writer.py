"""Batched, idempotent upsert for the bulk path.

Key = `place_source (provider, external_id)`; a content hash decides between skip / update. Inserts go
through executemany + RETURNING, a few thousand rows per transaction. Bulk-loaded places are
`approved` (official public registries) and get a `place_stats` row with NULL ratings — ratings are
never fabricated, and the scorer falls back to a neutral prior for NULL.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.db.base import new_uuid, utcnow
from app.infra.db.models import Category, Event, MenuItem, OpeningHour, Place, PlaceSource, PlaceStats
from app.infra.ingestion.bulk.common import BulkEvent, BulkPlace, BulkReport, chunked
from app.infra.ingestion.bulk.regions import RegionIndex
from app.infra.ingestion.pipeline import parse_time
from app.infra.ingestion.price import price_tier

BATCH_SIZE = 2000
OPTIONAL_TEXT_FIELDS = ("address", "road_address", "phone", "description")
ID_CHUNK = 900  # stays below SQLite's bound-parameter limit on old builds


@dataclass(frozen=True, slots=True)
class _Known:
    source_id: int
    place_id: int | None
    content_hash: str


def data_quality(p: BulkPlace, n_sources: int = 1) -> float:
    """Same checklist as the per-region pipeline; an estimated price does not count as price data."""
    checks = [
        bool(p.address or p.road_address),
        bool(p.phone),
        p.is_free or (p.price_per_person is not None and not p.price_is_estimated),
        bool(p.hours),
        bool(p.menus) or p.is_free,
        False,  # rating: public files have none
        False,  # thumbnail
        bool(p.description),
    ]
    return round(min(1.0, 0.85 * sum(checks) / len(checks) + 0.05 * min(n_sources, 3)), 3)


class BulkWriter:
    def __init__(self, session: AsyncSession, provider: str, regions: RegionIndex) -> None:
        self._s = session
        self._provider = provider
        self._regions = regions
        self._known: dict[str, _Known] = {}
        self._category_ids: dict[str, int] = {}
        self._closed: set[int] = set()
        self.seen: set[str] = set()
        self.report = BulkReport()

    async def prepare(self) -> None:
        rows = await self._s.stream(
            select(PlaceSource.external_id, PlaceSource.id, PlaceSource.place_id, PlaceSource.content_hash)
            .where(PlaceSource.provider == self._provider)
            .execution_options(yield_per=10_000)
        )
        self._known = {ext: _Known(sid, pid, h) async for ext, sid, pid, h in rows}
        self._category_ids = {c.code: c.id for c in (await self._s.scalars(select(Category))).all()}
        # "closed" means out of business (admins use rejected / hidden for quality decisions), so a
        # closed place that shows up again in the official open-stores file is simply open again.
        self._closed = set((await self._s.scalars(select(Place.id).where(Place.status == "closed"))).all())

    def has_category(self, code: str) -> bool:
        return code in self._category_ids

    async def write_all(self, places: Iterable[BulkPlace]) -> BulkReport:
        batch: list[BulkPlace] = []
        for place in places:
            batch.append(place)
            if len(batch) >= BATCH_SIZE:
                await self.write(batch)
                batch = []
        if batch:
            await self.write(batch)
        return self.report

    async def write(self, batch: Sequence[BulkPlace]) -> None:
        """One transaction per batch."""
        fresh: list[tuple[BulkPlace, int]] = []
        merges: list[BulkPlace] = []
        changed: list[tuple[BulkPlace, _Known]] = []
        reopen: list[int] = []
        for p in batch:
            if p.external_id in self.seen:
                self.report.skip("duplicate_id")
                continue
            self.seen.add(p.external_id)
            known = self._known.get(p.external_id)
            if known is not None and known.content_hash == p.content_hash:
                self.report.unchanged += 1
                if known.place_id in self._closed:
                    reopen.append(known.place_id)
                continue
            if known is not None and known.place_id is not None:
                changed.append((p, known))
                continue
            if p.merge_into_place_id is not None:
                merges.append(p)
                continue
            region_id = self._regions.locate(p.lat, p.lng, p.sido, p.sigungu)
            if region_id is None:
                self.report.skip("no_region")
                continue
            fresh.append((p, region_id))
        await self._insert(fresh)
        await self._merge(merges)
        await self._update(changed)
        if reopen:
            await self._s.execute(
                update(Place).where(Place.id.in_(reopen), Place.status == "closed").values(status="approved")
            )
            self._closed.difference_update(reopen)
            self.report.reopened += len(reopen)
        await self._s.commit()

    # --- new places --------------------------------------------------------------------------

    async def _insert(self, fresh: Sequence[tuple[BulkPlace, int]]) -> None:
        if not fresh:
            return
        now = utcnow()
        values = [
            {
                "public_id": new_uuid(),
                "region_id": region_id,
                "category_id": self._category_ids[p.category_code],
                "status": "approved",
                "approved_at": now,
                "last_verified_at": now,
                "images": [],
                **self._place_fields(p),
                "data_quality": data_quality(p),
            }
            for p, region_id in fresh
        ]
        # plain executemany (RETURNING degrades to row-by-row on SQLite); ids come back by public_id
        await self._s.execute(insert(Place), values)
        id_of: dict[str, int] = {}
        for chunk in chunked([v["public_id"] for v in values], ID_CHUNK):
            found = await self._s.execute(select(Place.public_id, Place.id).where(Place.public_id.in_(chunk)))
            id_of.update({public_id: pid for public_id, pid in found})
        place_ids = [id_of[v["public_id"]] for v in values]
        await self._s.execute(
            insert(PlaceStats), [{"place_id": pid, "aspect_scores": {}} for pid in place_ids]
        )
        await self._upsert_sources([(p, pid, 1.0) for (p, _), pid in zip(fresh, place_ids, strict=True)])
        await self._replace_children([(p, pid) for (p, _), pid in zip(fresh, place_ids, strict=True)])
        self.report.created += len(fresh)

    # --- cross-source duplicates: enrich the existing place ----------------------------------

    async def _merge(self, merges: Sequence[BulkPlace]) -> None:
        if not merges:
            return
        for group in _group_by_keys([self._merge_fields(p) for p in merges]):
            await self._s.execute(update(Place), group)
        pairs = [(p, p.merge_into_place_id) for p in merges if p.merge_into_place_id is not None]
        await self._upsert_sources([(p, pid, 0.9) for p, pid in pairs])
        await self._replace_children(pairs)
        self.report.merged += len(merges)

    # --- re-run with changed content ---------------------------------------------------------

    async def _update(self, changed: Sequence[tuple[BulkPlace, _Known]]) -> None:
        if not changed:
            return
        measured: set[int] = set()
        ids = [k.place_id for _, k in changed if k.place_id is not None]
        for chunk in chunked(ids, ID_CHUNK):
            rows = await self._s.scalars(
                select(Place.id).where(
                    Place.id.in_(chunk),
                    Place.price_is_estimated.is_(False),
                    Place.price_per_person.is_not(None),
                )
            )
            measured.update(rows.all())
        own, merged = [], []
        for p, known in changed:
            assert known.place_id is not None
            if p.merge_into_place_id is not None:
                merged.append({**self._merge_fields(p), "id": known.place_id})
                continue
            fields = self._place_fields(p)
            for key in OPTIONAL_TEXT_FIELDS:  # a source lacking a field must not erase another's value
                if fields[key] is None:
                    fields.pop(key)
            if p.price_is_estimated and known.place_id in measured:
                # never let a category prior overwrite a measured price (e.g. from 착한가격업소)
                for key in ("price_per_person", "price_is_estimated", "price_tier"):
                    fields.pop(key)
            own.append(
                {
                    "id": known.place_id,
                    "category_id": self._category_ids[p.category_code],
                    "last_verified_at": utcnow(),
                    "status": "approved",
                    **fields,
                }
            )
        for group in _group_by_keys(own) + _group_by_keys(merged):
            await self._s.execute(update(Place), group)
        pairs = [(p, k.place_id) for p, k in changed if k.place_id is not None]
        await self._upsert_sources([(p, pid, 1.0) for p, pid in pairs])
        await self._replace_children(pairs)
        self.report.updated += len(changed)

    # --- helpers -----------------------------------------------------------------------------

    @staticmethod
    def _place_fields(p: BulkPlace) -> dict[str, Any]:
        price = None if p.is_free else p.price_per_person
        # a source without photos (소진공, 표준데이터) must never wipe a photo another source gave us
        photo = {"thumbnail_url": p.thumbnail_url, "images": list(p.images)} if p.thumbnail_url else {}
        return {
            **photo,
            "name": p.name,
            "address": p.address,
            "road_address": p.road_address,
            "phone": p.phone,
            "description": p.description,
            "lat": p.lat,
            "lng": p.lng,
            "price_per_person": price,
            "price_is_estimated": bool(p.price_is_estimated and price is not None),
            "price_tier": price_tier(price, p.is_free),
            "is_free": p.is_free,
        }

    @staticmethod
    def _merge_fields(p: BulkPlace) -> dict[str, Any]:
        """Only what the enriching source really knows better: measured price, phone, quality."""
        assert p.merge_into_place_id is not None
        fields: dict[str, Any] = {
            "id": p.merge_into_place_id,
            "last_verified_at": utcnow(),
            "data_quality": data_quality(p, n_sources=2),
        }
        if p.price_per_person is not None and not p.price_is_estimated:
            fields.update(
                price_per_person=p.price_per_person,
                price_is_estimated=False,
                price_tier=price_tier(p.price_per_person, False),
            )
        if p.phone:
            fields["phone"] = p.phone
        if p.thumbnail_url:  # the real photo of the place is exactly what an enriching source is for
            fields.update(thumbnail_url=p.thumbnail_url, images=list(p.images))
        return fields

    async def _upsert_sources(self, rows: Sequence[tuple[BulkPlace, int, float]]) -> None:
        now = utcnow()
        new_rows: list[dict[str, Any]] = []
        updates: list[dict[str, Any]] = []
        for p, place_id, confidence in rows:
            known = self._known.get(p.external_id)
            values = {
                "place_id": place_id,
                "raw": p.raw,
                "fetched_at": now,
                "content_hash": p.content_hash,
                "match_confidence": confidence,
            }
            if known is None:
                new_rows.append({"provider": self._provider, "external_id": p.external_id, **values})
            else:
                updates.append({"id": known.source_id, **values})
                self._known[p.external_id] = _Known(known.source_id, place_id, p.content_hash)
        if new_rows:
            await self._s.execute(insert(PlaceSource), new_rows)
        if updates:
            await self._s.execute(update(PlaceSource), updates)

    async def _replace_children(self, rows: Sequence[tuple[BulkPlace, int]]) -> None:
        with_menus = [(p, pid) for p, pid in rows if p.menus]
        with_hours = [(p, pid) for p, pid in rows if p.hours]
        for chunk in chunked([pid for _, pid in with_menus], ID_CHUNK):
            await self._s.execute(
                delete(MenuItem).where(MenuItem.place_id.in_(chunk), MenuItem.source == self._provider)
            )
        for chunk in chunked([pid for _, pid in with_hours], ID_CHUNK):
            await self._s.execute(delete(OpeningHour).where(OpeningHour.place_id.in_(chunk)))
        menus = [
            {
                "place_id": pid,
                "name": m.name,
                "price": m.price,
                "is_signature": m.is_signature,
                "source": self._provider,
            }
            for p, pid in with_menus
            for m in p.menus
        ]
        hours = [
            {
                "place_id": pid,
                "dow": h.dow,
                "open_time": parse_time(h.open_time),
                "close_time": parse_time(h.close_time),
                "break_start": None,
                "break_end": None,
                "is_closed": h.is_closed,
            }
            for p, pid in with_hours
            for h in p.hours
        ]
        if menus:
            await self._s.execute(insert(MenuItem), menus)
        if hours:
            await self._s.execute(insert(OpeningHour), hours)

    async def close_unseen(self, scope: Iterable[str]) -> int:
        """Stores that vanished from a freshly loaded file are closed (never deleted).

        `scope` = the `raw["sido"]` values fully covered by this run, so a partial load is safe.
        """
        wanted = set(scope)
        unseen = [k.place_id for ext, k in self._known.items() if ext not in self.seen and k.place_id]
        closed = 0
        for chunk in chunked(unseen, ID_CHUNK):
            rows = await self._s.execute(
                select(PlaceSource.place_id, PlaceSource.raw).where(
                    PlaceSource.provider == self._provider, PlaceSource.place_id.in_(chunk)
                )
            )
            ids = [pid for pid, raw in rows if (raw or {}).get("sido") in wanted]
            if ids:
                await self._s.execute(
                    update(Place).where(Place.id.in_(ids), Place.status == "approved").values(status="closed")
                )
                closed += len(ids)
        await self._s.commit()
        self.report.closed += closed
        return closed

    async def write_events(self, events: Sequence[BulkEvent]) -> None:
        existing = {
            ext: eid
            for ext, eid in await self._s.execute(
                select(Event.external_id, Event.id).where(Event.provider == self._provider)
            )
        }
        inserts, updates = [], []
        for e in events:
            if e.external_id in self.seen:
                self.report.skip("duplicate_id")
                continue
            self.seen.add(e.external_id)
            region_id = self._regions.locate(e.lat, e.lng)
            if region_id is None:
                self.report.skip("no_region")
                continue
            values: dict[str, Any] = {
                "region_id": region_id,
                "category_id": self._category_ids.get(e.category_code),
                "title": e.title,
                "description": e.description,
                "address": e.address,
                "lat": e.lat,
                "lng": e.lng,
                "starts_on": e.starts_on,
                "ends_on": e.ends_on,
                "booking_url": e.booking_url,
                "status": "approved",
            }
            if e.images:
                values["images"] = list(e.images)
            if e.external_id in existing:
                updates.append({"id": existing[e.external_id], **values})
            else:
                inserts.append(
                    {
                        "public_id": new_uuid(),
                        "provider": self._provider,
                        "external_id": e.external_id,
                        "is_free": False,
                        **{"images": [], **values},
                    }
                )
        for chunk in chunked(inserts, BATCH_SIZE):
            await self._s.execute(insert(Event), list(chunk))
        for chunk in chunked(updates, BATCH_SIZE):
            await self._s.execute(update(Event), list(chunk))
        await self._s.commit()
        self.report.created += len(inserts)
        self.report.updated += len(updates)


def _group_by_keys(rows: Sequence[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """executemany needs homogeneous parameter sets."""
    groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(tuple(sorted(row)), []).append(row)
    return list(groups.values())
