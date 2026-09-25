"""Re-estimate stored prices after `data/bulk/price_prior.json` changes (2026-09-26).

An estimated price is written once, when a SEMAS row is loaded. When the prior is corrected — the
typical 요리 주점 was set at 25,000원 a head while the chain pubs next door carried 16,000원, so every
friends' evening ended in a chain — the places already in the database keep the old number. This walks
the places whose price is an estimate from SEMAS and writes the prior's current answer where it differs.

Measured prices (menus · 착한가격업소) are never touched: only `price_is_estimated` rows from `semas`.
Idempotent; commits in batches so the write lock is never held for long. Run by data sync (docs/57)
whenever price_prior.json changes, or by hand: `python -m app.cli ingest-bulk reprice`.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, update

from app.infra.db.models import Category, Place, PlaceSource
from app.infra.db.session import Database
from app.infra.ingestion.bulk import semas_store
from app.infra.ingestion.bulk.common import load_json
from app.infra.ingestion.bulk.price_prior import PricePrior

Log = Callable[[str], None]
BATCH = 2_000
PROVIDER = "semas"


@dataclass(slots=True)
class RepriceReport:
    seen: int = 0
    changed: int = 0
    unpriced: int = 0

    def line(self) -> str:
        return f"reprice: seen={self.seen} changed={self.changed} no_prior={self.unpriced}"


def new_price(
    prior: PricePrior, categories: dict[str, str], category: str, raw: dict[str, Any], name: str
) -> int | None:
    """The same rule as loading (semas_store.SemasMapper): a place moved by its name is priced as what it
    is, not as the code it was filed under."""
    code = str(raw.get("code") or "") or None
    moved = code is None or category != categories.get(code)
    return prior.estimate(category, raw.get("sido") or None, None if moved else code, name)


async def reprice(db: Database, *, log: Log = print) -> RepriceReport:
    report = RepriceReport()
    async with db.sessionmaker() as session:
        rows = (await session.execute(select(Category.code, Category.provider_mapping))).all()
        categories = semas_store.code_to_category((code, pm) for code, pm in rows)
        prior = PricePrior.from_data(load_json("price_prior.json"), load_json("regions_kr.json"))
        stmt = (
            select(Place.id, Place.name, Place.price_per_person, Category.code, PlaceSource.raw)
            .join(Category, Category.id == Place.category_id)
            .join(PlaceSource, (PlaceSource.place_id == Place.id) & (PlaceSource.provider == PROVIDER))
            .where(Place.price_is_estimated.is_(True), Place.is_free.is_(False))
            .execution_options(yield_per=20_000)
        )
        pending: list[tuple[int, int]] = []
        async for pid, name, price, category, raw in await session.stream(stmt):
            report.seen += 1
            data = raw if isinstance(raw, dict) else json.loads(raw or "{}")
            value = new_price(prior, categories, category, data, name or "")
            if value is None:
                report.unpriced += 1
                continue
            if value != price:
                pending.append((pid, value))
        for start in range(0, len(pending), BATCH):
            for pid, value in pending[start : start + BATCH]:
                await session.execute(update(Place).where(Place.id == pid).values(price_per_person=value))
            await session.commit()
            report.changed += len(pending[start : start + BATCH])
    log(report.line())
    return report
