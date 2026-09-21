"""fetch → hash-diff → upsert place_source → match/merge → place → children/stats → search outbox.

The same code path serves every provider, including the `file` provider used for seed data.
Places from untrusted providers land as `pending` and wait for admin approval.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import time
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.db.base import utcnow
from app.infra.db.models import (
    Category,
    Event,
    IngestionJob,
    MenuItem,
    OpeningHour,
    Place,
    PlaceSource,
    PlaceStats,
    PlaceTag,
    PopularTime,
    Region,
    SearchOutbox,
    Tag,
)
from app.infra.ingestion import dedupe
from app.infra.ingestion.base import NormalizedEvent, NormalizedPlace, PlaceProvider, RawPlace, RegionRef
from app.infra.ingestion.price import price_per_person, price_tier
from app.infra.ingestion.stats import refresh_region_stats

logger = logging.getLogger(__name__)

PROVIDER_MAPPING_KEY = {"kakao_local": "kakao", "naver_search": "naver", "google_places": "google"}
AUTO_TAG_GROUP = "auto"


@dataclass(slots=True)
class IngestionReport:
    fetched: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


def region_ref(region: Region) -> RegionRef:
    return RegionRef(
        slug=region.slug,
        name=region.name,
        center_lat=region.center_lat,
        center_lng=region.center_lng,
        radius_m=region.radius_m,
        area_code=region.area_code,
        search_keywords=tuple(region.search_keywords or ()),
    )


def parse_time(value: str | None) -> time | None:
    if not value:
        return None
    hh, mm = value.split(":")[:2]
    return time(int(hh) % 24, int(mm))


class CategoryResolver:
    def __init__(self, categories: list[Category]) -> None:
        self._by_code = {c.code: c for c in categories}
        self._categories = categories

    def resolve(self, provider: str, code: str | None, provider_categories: list[str]) -> Category | None:
        if code and code in self._by_code:
            return self._by_code[code]
        key = PROVIDER_MAPPING_KEY.get(provider, provider)
        best: Category | None = None
        for wanted in provider_categories:  # most specific first
            if wanted in self._by_code:
                return self._by_code[wanted]
            for cat in self._categories:
                mapped = (cat.provider_mapping or {}).get(key) or []
                if any(m == wanted or (len(m) > 1 and m in wanted) for m in mapped) and (
                    best is None or cat.code.count(".") > best.code.count(".")
                ):
                    best = cat
            if best is not None:
                return best
        return None


class IngestionPipeline:
    def __init__(self, session: AsyncSession, trusted_providers: list[str]) -> None:
        self._s = session
        self._trusted = set(trusted_providers)

    async def run(
        self, provider: PlaceProvider, region: Region, job: IngestionJob | None = None
    ) -> IngestionReport:
        report = IngestionReport()
        resolver = CategoryResolver(list((await self._s.scalars(select(Category))).all()))
        tags = {t.name: t for t in (await self._s.scalars(select(Tag))).all()}
        rows = (await self._s.scalars(select(Place).where(Place.region_id == region.id))).all()
        existing = [dedupe.ExistingPlace(p.id, p.name, p.lat, p.lng, p.phone) for p in rows]
        if job is not None:
            job.status, job.started_at = "running", utcnow()

        try:
            async for raw in provider.fetch(region_ref(region), job.cursor if job else None):
                report.fetched += 1
                try:
                    async with self._s.begin_nested():
                        await self._ingest_one(provider, raw, region, resolver, tags, existing, report)
                except Exception as exc:
                    report.failed += 1
                    report.errors.append(f"{raw.external_id}: {exc}")
                    logger.warning("ingest failed provider=%s id=%s: %s", raw.provider, raw.external_id, exc)
            await self._s.flush()
            await refresh_region_stats(self._s, region.id)
            status, error = "succeeded", None
        except Exception as exc:  # provider-level failure (auth, quota, network)
            status, error = "failed", str(exc)
            report.errors.append(str(exc))
            logger.exception("ingestion job failed provider=%s region=%s", provider.name, region.slug)
        if job is not None:
            job.status, job.error, job.finished_at = status, error, utcnow()
            job.fetched_count, job.created_count = report.fetched, report.created
            job.updated_count, job.failed_count = report.updated, report.failed
        return report

    async def _ingest_one(
        self,
        provider: PlaceProvider,
        raw: RawPlace,
        region: Region,
        resolver: CategoryResolver,
        tags: dict[str, Tag],
        existing: list[dedupe.ExistingPlace],
        report: IngestionReport,
    ) -> None:
        source = await self._s.scalar(
            select(PlaceSource).where(
                PlaceSource.provider == raw.provider, PlaceSource.external_id == raw.external_id
            )
        )
        if source is not None and source.content_hash == raw.content_hash:
            source.fetched_at = utcnow()
            report.skipped += 1
            return
        normalized = provider.normalize(raw)
        if normalized is None:
            report.failed += 1
            return
        if source is None:
            source = PlaceSource(provider=raw.provider, external_id=raw.external_id, raw=raw.raw)
            self._s.add(source)
        source.raw, source.content_hash, source.fetched_at = raw.raw, raw.content_hash, utcnow()

        category = resolver.resolve(raw.provider, normalized.category_code, normalized.provider_categories)
        if isinstance(normalized, NormalizedEvent):
            created = await self._upsert_event(normalized, region, category)
        else:
            if category is None:
                report.failed += 1
                report.errors.append(f"{raw.external_id}: unmapped category {normalized.provider_categories}")
                return
            created = await self._upsert_place(normalized, source, region, category, tags, existing)
        report.created += int(created)
        report.updated += int(not created)

    async def _upsert_event(self, n: NormalizedEvent, region: Region, category: Category | None) -> bool:
        event = await self._s.scalar(
            select(Event).where(Event.provider == n.provider, Event.external_id == n.external_id)
        )
        created = event is None
        if event is None:
            status = "approved" if n.provider in self._trusted else "pending"
            event = Event(provider=n.provider, external_id=n.external_id, region_id=region.id, status=status)
            self._s.add(event)
        event.title, event.description, event.address = n.title, n.description, n.address
        event.lat, event.lng, event.starts_on, event.ends_on = n.lat, n.lng, n.starts_on, n.ends_on
        event.price, event.is_free, event.booking_url, event.images = (
            n.price,
            n.is_free,
            n.booking_url,
            n.images,
        )
        event.category_id = category.id if category else None
        return created

    async def _upsert_place(
        self,
        n: NormalizedPlace,
        source: PlaceSource,
        region: Region,
        category: Category,
        tags: dict[str, Tag],
        existing: list[dedupe.ExistingPlace],
    ) -> bool:
        trusted = n.provider in self._trusted
        place: Place | None = await self._s.get(Place, source.place_id) if source.place_id else None
        confidence = 1.0
        if place is None:
            match = dedupe.find_match(n.name, n.lat, n.lng, n.phone, existing)
            if match is not None:
                place, confidence = await self._s.get(Place, match.place_id), match.confidence
        created = place is None
        if place is None:
            place = Place(
                region_id=region.id,
                category_id=category.id,
                name=n.name,
                lat=n.lat,
                lng=n.lng,
                status="approved" if trusted else "pending",
                approved_at=utcnow() if trusted else None,
                images=[],
            )
            self._s.add(place)
        self._apply_fields(place, n, category, overwrite=created or trusted)
        await self._s.flush()
        if created:
            existing.append(dedupe.ExistingPlace(place.id, place.name, place.lat, place.lng, place.phone))
        source.place_id, source.match_confidence = place.id, confidence

        await self._replace_children(place, n, tags, overwrite=created or trusted)
        await self._upsert_stats(place.id, n)
        place.data_quality = await self._data_quality(place, n)
        place.last_verified_at = utcnow()
        self._s.add(SearchOutbox(entity="place", entity_id=place.id, op="upsert"))
        return created

    @staticmethod
    def _apply_fields(place: Place, n: NormalizedPlace, category: Category, *, overwrite: bool) -> None:
        derived_price = n.price_per_person if n.price_per_person is not None else price_per_person(n.menus)
        values: dict[str, Any] = {
            "name": n.name,
            "address": n.address,
            "road_address": n.road_address,
            "phone": n.phone,
            "description": n.description,
            "thumbnail_url": n.thumbnail_url,
            "price_per_person": None if n.is_free else derived_price,
        }
        for attr, value in values.items():
            if value is not None and (overwrite or getattr(place, attr) in (None, "")):
                setattr(place, attr, value)
        if derived_price is not None and not n.is_free and (overwrite or place.price_is_estimated):
            # a real menu / provider price always beats the bulk loader's category prior
            place.price_per_person, place.price_is_estimated = derived_price, False
        if overwrite:
            place.lat, place.lng, place.category_id, place.is_free = n.lat, n.lng, category.id, n.is_free
        if n.images and (overwrite or not place.images):
            place.images = n.images
        place.price_tier = price_tier(place.price_per_person, place.is_free)

    async def _replace_children(
        self, place: Place, n: NormalizedPlace, tags: dict[str, Tag], *, overwrite: bool
    ) -> None:
        pid = place.id
        if n.menus and overwrite:
            await self._s.execute(delete(MenuItem).where(MenuItem.place_id == pid))
            self._s.add_all(
                MenuItem(
                    place_id=pid, name=m.name, price=m.price, is_signature=m.is_signature, source=n.provider
                )
                for m in n.menus
            )
        if n.opening_hours and overwrite:
            await self._s.execute(delete(OpeningHour).where(OpeningHour.place_id == pid))
            self._s.add_all(
                OpeningHour(
                    place_id=pid,
                    dow=h.dow,
                    open_time=parse_time(h.open_time),
                    close_time=parse_time(h.close_time),
                    break_start=parse_time(h.break_start),
                    break_end=parse_time(h.break_end),
                    is_closed=h.is_closed,
                )
                for h in n.opening_hours
            )
        if n.popular_times and overwrite:
            await self._s.execute(delete(PopularTime).where(PopularTime.place_id == pid))
            self._s.add_all(
                PopularTime(place_id=pid, dow=d, hour=h, congestion=max(0.0, min(1.0, c)), source=n.provider)
                for d, h, c in n.popular_times
            )
        if n.tags:
            # admin / llm tags are never overwritten by a provider re-fetch
            await self._s.execute(
                delete(PlaceTag).where(PlaceTag.place_id == pid, PlaceTag.source.in_(["file", "provider"]))
            )
            kept = set((await self._s.scalars(select(PlaceTag.tag_id).where(PlaceTag.place_id == pid))).all())
            for name, weight in n.tags.items():
                tag = tags.get(name)
                if tag is None:
                    tag = Tag(name=name, group=AUTO_TAG_GROUP, is_selectable=False)
                    self._s.add(tag)
                    await self._s.flush()
                    tags[name] = tag
                if tag.id not in kept:
                    source = "file" if n.provider == "file" else "provider"
                    self._s.add(PlaceTag(place_id=pid, tag_id=tag.id, weight=float(weight), source=source))

    async def _upsert_stats(self, place_id: int, n: NormalizedPlace) -> None:
        stats = await self._s.get(PlaceStats, place_id)
        if stats is None:
            stats = PlaceStats(place_id=place_id, aspect_scores={})
            self._s.add(stats)
        if n.rating_avg is not None and n.rating_count >= (stats.rating_count or 0):
            stats.rating_avg, stats.rating_count = float(n.rating_avg), n.rating_count
        if n.sentiment_score is not None and n.sentiment_count > 0:
            stats.sentiment_score, stats.sentiment_count = float(n.sentiment_score), n.sentiment_count
            stats.aspect_scores = dict(n.aspect_scores)

    async def _data_quality(self, place: Place, n: NormalizedPlace) -> float:
        checks = [
            bool(place.address or place.road_address),
            bool(place.phone),
            place.is_free or place.price_per_person is not None,
            bool(n.opening_hours),
            bool(n.menus) or place.is_free,
            n.rating_avg is not None,
            bool(place.thumbnail_url),
            bool(place.description),
        ]
        sources = len(
            (await self._s.scalars(select(PlaceSource.id).where(PlaceSource.place_id == place.id))).all()
        )
        return round(min(1.0, 0.85 * sum(checks) / len(checks) + 0.05 * min(sources, 3)), 3)
