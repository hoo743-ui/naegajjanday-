"""Data sync (docs/57): the data files that ship with the code reach the production database by themselves.

A deploy used to need three commands in Render Shell afterwards (`seed-config`, `ingest-bulk delta <file>`,
`ingest-bulk universities --step load`); forgetting one left the web showing a feature without its data.
Now every shipped file is an *item* with a content hash, and `data_sync` (a table in the same database, so on
the persistent disk) remembers the hash last applied. `sync` applies, in order:

1. `seed` — data/seed/{categories,tags,regions,purposes}.json through `load_config` (what `seed-config` does)
2. `delta/<name>` — every data/bulk/delta/*.json, sorted by name: `delta.load` for new places,
   `tourapi_hours.load_file` for opening-hour answers (docs/55)
3. `anchors/universities.json` — `universities.load`

and skips an item whose hash is already recorded. Every loader is idempotent on its own (upserts keyed by
code / external id, unchanged rows skipped), so a re-run, a crash half-way or an empty database is safe: an
item is recorded only after it succeeded, and a failed item is tried again next time. Bulk writes commit
every `BulkWriter.BATCH_SIZE` rows, so the SQLite write lock is never held for long.

Render cannot run this in a preDeployCommand — the persistent disk is not mounted there — so the app starts
it as a background task after startup (production only by default), under a file lock so only one process
runs it. Admins see the state and can run it again from 설정 · DB.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import sys
import tempfile
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import IO, Any, Literal

from sqlalchemy import select
from sqlalchemy.engine import make_url

from app.core.config import API_ROOT, Settings
from app.core.logging import get_logger
from app.infra.db.base import utcnow
from app.infra.db.models import DataSync
from app.infra.db.session import Database

logger = get_logger(__name__)
Log = Callable[[str], None]

SEED_FILES = ("categories.json", "tags.json", "regions.json", "purposes.json")  # what `load_config` reads
DELTA_DIR = API_ROOT / "data" / "bulk" / "delta"
UNIVERSITIES_PATH = API_ROOT / "data" / "anchors" / "universities.json"
RUN_KEY = "@run"  # the row that remembers the last whole run (not an item)

Kind = Literal["seed", "delta", "anchor"]
Action = Literal["applied", "skipped", "failed"]


@dataclass(frozen=True, slots=True)
class Item:
    key: str
    kind: Kind
    label: str
    paths: tuple[Path, ...]
    content_hash: str


@dataclass(slots=True)
class ItemResult:
    key: str
    action: Action
    summary: str | None = None
    error: str | None = None
    seconds: float = 0.0


@dataclass(slots=True)
class SyncReport:
    started_at: datetime
    finished_at: datetime | None = None
    locked: bool = False  # another process was already syncing → nothing done here
    results: list[ItemResult] = field(default_factory=list)

    def count(self, action: Action) -> int:
        return sum(1 for r in self.results if r.action == action)

    def line(self) -> str:
        if self.locked:
            return "another sync is running — skipped"
        return (
            f"applied={self.count('applied')} skipped={self.count('skipped')} failed={self.count('failed')}"
        )


@dataclass(frozen=True, slots=True)
class ItemState:
    key: str
    kind: Kind
    label: str
    files: list[str]
    applied: bool  # the file as it is now has been applied
    applied_at: datetime | None
    summary: str | None
    last_error: str | None
    attempted_at: datetime | None


@dataclass(frozen=True, slots=True)
class SyncStatus:
    running: bool
    last_started_at: datetime | None
    last_finished_at: datetime | None
    last_summary: str | None
    items: list[ItemState]


@dataclass(frozen=True, slots=True)
class Sources:
    seed_dir: Path
    delta_dir: Path = DELTA_DIR
    universities: Path = UNIVERSITIES_PATH


def default_sources(settings: Settings) -> Sources:
    return Sources(seed_dir=settings.seed_dir)


def _hash(paths: tuple[Path, ...]) -> str:
    h = hashlib.sha256()
    for p in paths:
        h.update(p.name.encode())
        h.update(b"\0")
        h.update(p.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def plan(sources: Sources) -> list[Item]:
    """Every shipped data file, in the order it must be applied (seed first: deltas need its categories)."""
    items: list[Item] = []
    seed = tuple(p for p in (sources.seed_dir / n for n in SEED_FILES) if p.is_file())
    if seed:
        label = "설정 데이터 (카테고리 · 태그 · 지역 · 목적 · 코스 틀)"
        items.append(Item("seed", "seed", label, seed, _hash(seed)))
    if sources.delta_dir.is_dir():
        for p in sorted(sources.delta_dir.glob("*.json")):
            items.append(Item(f"delta/{p.name}", "delta", f"장소 추가분 {p.stem}", (p,), _hash((p,))))
    if sources.universities.is_file():
        u = (sources.universities,)
        items.append(Item(f"anchors/{u[0].name}", "anchor", "대학교 캠퍼스", u, _hash(u)))
    return items


# --- lock -----------------------------------------------------------------------------------------------

_running = False  # this process is syncing (the admin page shows it)


def lock_path(settings: Settings) -> Path:
    """Next to the SQLite file (the persistent disk); a temp file for PostgreSQL / in-memory databases."""
    if settings.is_sqlite:
        database = make_url(settings.database_url).database
        if database and database != ":memory:":
            db_path = Path(database).resolve()
            return db_path.with_name(db_path.name + ".data-sync.lock")
    return Path(tempfile.gettempdir()) / "naegajjanday.data-sync.lock"


def _try_lock(fh: IO[bytes]) -> bool:
    try:
        if sys.platform == "win32":
            import msvcrt

            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def _unlock(fh: IO[bytes]) -> None:
    with contextlib.suppress(OSError):
        if sys.platform == "win32":
            import msvcrt

            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


@contextlib.contextmanager
def file_lock(path: Path) -> Iterator[bool]:
    """An OS lock (released by the OS if the process dies — no stale lock after a crashed deploy).
    Yields False when another process holds it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as fh:
        got = _try_lock(fh)
        try:
            yield got
        finally:
            if got:
                _unlock(fh)


def is_running() -> bool:
    return _running


# --- apply ----------------------------------------------------------------------------------------------


async def _ensure_table(db: Database) -> None:
    """`db init` creates it; this keeps a DB that skipped `db init` (or a Postgres before 0013) working."""
    async with db.engine.begin() as conn:
        await conn.run_sync(lambda c: DataSync.__table__.create(c, checkfirst=True))  # type: ignore[attr-defined]


async def _apply(db: Database, item: Item, log: Log) -> str:
    if item.kind == "seed":
        from app.infra.ingestion.config_loader import load_config

        async with db.sessionmaker() as session:
            report = await load_config(session, item.paths[0].parent)
            await session.commit()
        return (
            f"categories={report.categories} tags={report.tags} regions={report.regions} "
            f"purposes={report.purposes} templates={report.templates}"
        )
    if item.kind == "delta":
        return await _apply_delta(db, item.paths[0], log)
    from app.infra.ingestion.bulk import universities

    return (await universities.load(db, path=item.paths[0], log=log)).line()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


async def _apply_delta(db: Database, path: Path, log: Log) -> str:
    """data/bulk/delta holds two shapes: new places (`places`, bulk/delta.py) and TourAPI opening-hour
    answers (`intros`, bulk/tourapi_hours.py `--export`, docs/55). Both loaders are idempotent."""
    head = _read_json(path)
    if isinstance(head, dict) and "places" in head:
        from app.infra.ingestion.bulk import delta

        return (await delta.load(db, path, log=log)).line()
    if isinstance(head, dict) and "intros" in head:
        from app.infra.ingestion.bulk import tourapi_hours

        return (await tourapi_hours.load_file(db, path, log=log)).line()
    raise ValueError(f"{path.name}: neither `places` (a place delta) nor `intros` (opening hours)")


async def _record(db: Database, key: str, **values: Any) -> None:
    async with db.sessionmaker() as session:
        row = await session.get(DataSync, key)
        if row is None:
            row = DataSync(key=key)
            session.add(row)
        for name, value in values.items():
            setattr(row, name, value)
        await session.commit()


async def _applied_hashes(db: Database) -> dict[str, DataSync]:
    async with db.sessionmaker() as session:
        return {r.key: r for r in (await session.scalars(select(DataSync))).all()}


async def sync(
    db: Database,
    settings: Settings,
    *,
    force: bool = False,
    sources: Sources | None = None,
    log: Log | None = None,
) -> SyncReport:
    """Apply every item whose file changed since it was last applied (`force`: all of them)."""
    global _running
    say: Log = log or (lambda m: logger.info("data_sync.log", message=m))
    report = SyncReport(started_at=utcnow())
    with file_lock(lock_path(settings)) as got:
        if not got or _running:
            report.locked = True
            say(report.line())
            return report
        _running = True
        try:
            await _ensure_table(db)
            known = await _applied_hashes(db)
            await _record(db, RUN_KEY, attempted_at=report.started_at)
            for item in plan(sources or default_sources(settings)):
                row = known.get(item.key)
                if not force and row is not None and row.content_hash == item.content_hash:
                    report.results.append(ItemResult(item.key, "skipped"))
                    continue
                say(f"{item.key}: applying")
                started = time.perf_counter()
                attempted = utcnow()
                try:
                    summary = await _apply(db, item, say)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # recorded, tried again next time; the next item still runs
                    logger.exception("data_sync.item_failed", key=item.key)
                    error = f"{type(exc).__name__}: {exc}"[:2000]
                    report.results.append(
                        ItemResult(item.key, "failed", error=error, seconds=time.perf_counter() - started)
                    )
                    await _record(db, item.key, last_error=error, attempted_at=attempted)
                    continue
                seconds = time.perf_counter() - started
                report.results.append(ItemResult(item.key, "applied", summary=summary, seconds=seconds))
                await _record(
                    db,
                    item.key,
                    content_hash=item.content_hash,
                    applied_at=utcnow(),
                    summary=summary,
                    last_error=None,
                    attempted_at=attempted,
                )
                say(f"{item.key}: {summary} ({seconds:.1f}s)")
                await asyncio.sleep(0)  # let requests in between items
            report.finished_at = utcnow()
            await _record(db, RUN_KEY, applied_at=report.finished_at, summary=report.line())
        finally:
            _running = False
    logger.info(
        "data_sync.done",
        applied=report.count("applied"),
        skipped=report.count("skipped"),
        failed=report.count("failed"),
    )
    return report


async def status(db: Database, settings: Settings, *, sources: Sources | None = None) -> SyncStatus:
    await _ensure_table(db)
    known = await _applied_hashes(db)
    items = []
    for item in plan(sources or default_sources(settings)):
        row = known.get(item.key)
        items.append(
            ItemState(
                key=item.key,
                kind=item.kind,
                label=item.label,
                files=[p.name for p in item.paths],
                applied=row is not None and row.content_hash == item.content_hash,
                applied_at=row.applied_at if row else None,
                summary=row.summary if row else None,
                last_error=row.last_error if row else None,
                attempted_at=row.attempted_at if row else None,
            )
        )
    run = known.get(RUN_KEY)
    return SyncStatus(
        running=_running,
        last_started_at=run.attempted_at if run else None,
        last_finished_at=run.applied_at if run else None,
        last_summary=run.summary if run else None,
        items=items,
    )


def enabled_on_start(settings: Settings) -> bool:
    return settings.is_production if settings.data_sync_on_start is None else settings.data_sync_on_start


async def run_on_start(db: Database, settings: Settings) -> None:
    """The startup task: wait a moment (health check first), then sync; never crashes the app."""
    await asyncio.sleep(settings.data_sync_delay_s)
    try:
        report = await sync(db, settings)
    except asyncio.CancelledError:
        logger.warning("data_sync.cancelled")
        raise
    except Exception:
        logger.exception("data_sync.failed")
        return
    logger.info("data_sync.on_start", result=report.line())
