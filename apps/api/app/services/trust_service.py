"""Loads the stored facts a trust line reads (app.domain.trust) for a course's places, one query per table."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.media import image_key
from app.domain.recommendation.familiarity import familiarity_rules, parse_opened_on
from app.domain.trust import PROVIDER_ALIASES, TrustFacts
from app.infra.db.models import MenuItem, Place, PlaceSource

CHUNK = 400  # ids per IN (...) — SQLite allows 999 bound values
# place_source rows that are a designation (app.domain.trust.DESIGNATIONS) or a measured visit rank
FACT_PROVIDERS = ("goodprice", "tmap_hub", *PROVIDER_ALIASES)


def _raw(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        found = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return found if isinstance(found, dict) else {}


async def load_trust_facts(session: AsyncSession, place_ids: Sequence[int]) -> dict[int, TrustFacts]:
    """place id → what the database holds beyond the candidate row. Places with nothing are left out."""
    ids = sorted({i for i in place_ids if i})
    licence_keys = dict(familiarity_rules().opened_on_sources or {})
    providers: dict[int, set[str]] = {}
    licence: dict[int, date] = {}
    visit: dict[int, dict[str, Any]] = {}
    menus: dict[int, tuple[bool, int, str, str]] = {}
    photos: dict[int, int] = {}
    for i in range(0, len(ids), CHUNK):
        chunk = ids[i : i + CHUNK]
        rows = await session.execute(
            select(PlaceSource.place_id, PlaceSource.provider, PlaceSource.raw).where(
                PlaceSource.place_id.in_(chunk),
                PlaceSource.provider.in_(sorted({*FACT_PROVIDERS, *licence_keys})),
            )
        )
        for pid, provider, raw in rows.all():
            if pid is None:
                continue
            if provider in licence_keys:
                if (on := parse_opened_on(_raw(raw), licence_keys[provider])) is not None:
                    licence[pid] = min(on, licence.get(pid, on))
                continue
            if provider == "tmap_hub":
                data = _raw(raw)
                rank = data.get("rank")
                if isinstance(rank, int) and (pid not in visit or rank < visit[pid]["rank"]):
                    visit[pid] = data
                continue
            providers.setdefault(pid, set()).add(provider)
        menu_rows = await session.execute(
            select(
                MenuItem.place_id, MenuItem.name, MenuItem.price, MenuItem.is_signature, MenuItem.source
            ).where(MenuItem.place_id.in_(chunk), MenuItem.price > 0)
        )
        for pid, name, price, signature, source in menu_rows.all():
            key = (not signature, int(price), str(name).strip(), str(source or ""))
            if key[2] and (pid not in menus or key < menus[pid]):
                menus[pid] = key
        image_rows = await session.execute(
            select(Place.id, Place.thumbnail_url, Place.images).where(Place.id.in_(chunk))
        )
        for pid, thumb, images in image_rows.all():
            urls = [u for u in [thumb, *(images or [])] if isinstance(u, str) and u]
            if urls:
                photos[pid] = len({image_key(u) for u in urls})
    out: dict[int, TrustFacts] = {}
    for pid in ids:
        v, menu = visit.get(pid) or {}, menus.get(pid)
        facts = TrustFacts(
            providers=frozenset(providers.get(pid, ())),
            licence_on=licence.get(pid),
            visit_rank=v.get("rank") if v else None,
            visit_area=str(v.get("district") or "") or None if v else None,
            visit_month=str(v.get("month") or "") or None if v else None,
            menu_name=menu[2] if menu else None,
            menu_price=menu[1] if menu else None,
            menu_source=menu[3] if menu else None,
            photos=photos.get(pid, 0),
        )
        if facts != TrustFacts():
            out[pid] = facts
    return out
