"""A small set of new places shipped as a file (docs/51): built once from the raw open data on a machine
that has it, loaded anywhere with one command — the production disk has neither the raw files nor the
memory to re-read 2 GB of them.

`export_semas_gated` keeps the rows a name-gated code lets through (bulk_rules › semas › name_gated_codes:
사진촬영업 → 셀프 사진관); `load` writes them through the same BulkWriter as a full load, so a later full
reload finds them by the same external ids and nothing is duplicated.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.infra.db.session import Database
from app.infra.ingestion.base import NormalizedHour, NormalizedMenu
from app.infra.ingestion.bulk import semas_store
from app.infra.ingestion.bulk.common import BulkPlace, BulkReport, iter_csv, load_json
from app.infra.ingestion.bulk.regions import RegionIndex
from app.infra.ingestion.bulk.writer import BulkWriter

Log = Callable[[str], None]


async def export_semas_gated(db: Database, zip_path: Path, out: Path, *, log: Log = print) -> int:
    from app.infra.ingestion.bulk.runner import _semas_mapper  # the full load's mapper, same rules

    spec = load_json("regions_kr.json")
    async with db.sessionmaker() as session:
        mapper = await _semas_mapper(session, spec)
    gated = set(mapper.gated)
    rows: list[dict[str, Any]] = []
    for member in semas_store.ordered_members(zip_path, ()):
        for row in iter_csv(zip_path, member):
            code = row.get(semas_store.COL_CODE) or ""
            if code not in gated or mapper.skip_reason(row) is not None:
                continue
            if mapper.category_for(row) != mapper.gated[code][0]:
                continue  # a café whose name is not a tarot place stays where the full load put it
            place = mapper.build(row)
            rows.append({k: v for k, v in asdict(place).items() if k != "raw"})
        log(f"  {member}: {len(rows)}")
    _write(out, {"provider": semas_store.PROVIDER, "places": rows})
    return len(rows)


def _write(out: Path, payload: dict[str, Any]) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def _read(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def _place(d: dict[str, Any]) -> BulkPlace:
    return BulkPlace(
        **{
            **d,
            "menus": [NormalizedMenu(**m) for m in d.get("menus") or []],
            "hours": [NormalizedHour(**h) for h in d.get("hours") or []],
        }
    )


async def load(db: Database, path: Path, *, log: Log = print) -> BulkReport:
    data = _read(path)
    places = [_place(p) for p in data["places"]]
    spec = load_json("regions_kr.json")
    async with db.sessionmaker() as session:
        index = await RegionIndex.load(session, spec)
        writer = BulkWriter(session, str(data["provider"]), index)
        # only these ids: the production box has 512 MB, and knowing all 700k sources is not needed
        await writer.prepare(only_ids={p.external_id for p in places})
        await writer.write_all(places)
        await session.commit()
    log(writer.report.line())
    return writer.report
