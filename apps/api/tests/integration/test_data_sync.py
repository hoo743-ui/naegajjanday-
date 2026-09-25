"""Data sync (docs/57): shipped data files reach a database once, are skipped after, and again when changed."""

from __future__ import annotations

import asyncio
import shutil
from collections.abc import AsyncIterator
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.core.config import API_ROOT, Settings
from app.infra.db.models import Category, DataSync, Place, PlaceSource
from app.infra.db.session import Database
from app.infra.ingestion.bulk import delta
from app.infra.ingestion.bulk.common import BulkPlace
from app.services import data_sync

SEED_DIR = API_ROOT / "data" / "seed"


def _settings(db_file: Path) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        log_level="WARNING",
        database_url=f"sqlite+aiosqlite:///{db_file.as_posix()}",
        jwt_secret="test-secret-test-secret-test-secret-1234",
    )


@pytest_asyncio.fixture
async def empty_db(tmp_path: Path) -> AsyncIterator[tuple[Database, Settings]]:
    """A database with tables and nothing else — the first deploy of a new disk."""
    settings = _settings(tmp_path / "sync.db")
    db = Database(settings)
    await db.create_all()
    try:
        yield db, settings
    finally:
        await db.dispose()


def _cinema(name: str, ext: str = "t-1") -> BulkPlace:
    return BulkPlace(
        provider="test_sync",
        external_id=ext,
        name=name,
        category_code="activity.cinema",
        lat=37.5563,  # 홍대 — a seeded hotspot, so the place gets a region
        lng=126.9236,
        sido="서울특별시",
        sigungu="마포구",
        price_per_person=15000,
    )


@pytest.fixture
def sources(tmp_path: Path) -> data_sync.Sources:
    seed = tmp_path / "seed"
    seed.mkdir()
    for name in data_sync.SEED_FILES:
        shutil.copy(SEED_DIR / name, seed / name)
    deltas = tmp_path / "delta"
    delta.write_delta(deltas / "cinemas.json", "test_sync", [_cinema("씨네 홍대")])
    return data_sync.Sources(seed_dir=seed, delta_dir=deltas, universities=tmp_path / "none.json")


def _actions(report: data_sync.SyncReport) -> dict[str, str]:
    return {r.key: r.action for r in report.results}


async def _place_names(db: Database) -> list[str]:
    async with db.sessionmaker() as s:
        rows = await s.scalars(
            select(Place.name)
            .join(PlaceSource, PlaceSource.place_id == Place.id)
            .where(PlaceSource.provider == "test_sync")
        )
        return sorted(rows.all())


async def test_applies_once_skips_after_and_again_when_a_file_changes(
    empty_db: tuple[Database, Settings], sources: data_sync.Sources
) -> None:
    db, settings = empty_db
    first = await data_sync.sync(db, settings, sources=sources, log=lambda _m: None)
    assert _actions(first) == {"seed": "applied", "delta/cinemas.json": "applied"}
    assert await _place_names(db) == ["씨네 홍대"]
    async with db.sessionmaker() as s:
        assert await s.scalar(select(Category.id).where(Category.code == "activity.cinema"))

    second = await data_sync.sync(db, settings, sources=sources, log=lambda _m: None)
    assert _actions(second) == {"seed": "skipped", "delta/cinemas.json": "skipped"}

    # a new delta build: the one file changed is applied, the seed is not touched
    delta.write_delta(
        sources.delta_dir / "cinemas.json",
        "test_sync",
        [_cinema("씨네 홍대 (새 이름)"), _cinema("둘째", "t-2")],
    )
    third = await data_sync.sync(db, settings, sources=sources, log=lambda _m: None)
    assert _actions(third) == {"seed": "skipped", "delta/cinemas.json": "applied"}
    assert await _place_names(db) == ["둘째", "씨네 홍대 (새 이름)"]  # updated in place, not duplicated

    # a new file next to the old ones is picked up on its own
    delta.write_delta(sources.delta_dir / "extra.json", "test_sync", [_cinema("셋째", "t-3")])
    fourth = await data_sync.sync(db, settings, sources=sources, log=lambda _m: None)
    assert _actions(fourth)["delta/extra.json"] == "applied"
    assert _actions(fourth)["delta/cinemas.json"] == "skipped"

    status = await data_sync.status(db, settings, sources=sources)
    assert all(i.applied for i in status.items) and status.last_finished_at is not None
    assert status.last_summary == "applied=1 skipped=2 failed=0"


async def test_force_applies_everything_and_changes_nothing(
    empty_db: tuple[Database, Settings], sources: data_sync.Sources
) -> None:
    db, settings = empty_db
    await data_sync.sync(db, settings, sources=sources, log=lambda _m: None)
    again = await data_sync.sync(db, settings, sources=sources, force=True, log=lambda _m: None)
    assert set(_actions(again).values()) == {"applied"}
    assert await _place_names(db) == ["씨네 홍대"]


async def test_a_failed_file_is_recorded_and_tried_again(
    empty_db: tuple[Database, Settings], sources: data_sync.Sources
) -> None:
    db, settings = empty_db
    bad = replace(_cinema("x", "bad"), category_code="activity.nope")
    delta.write_delta(sources.delta_dir / "a_bad.json", "test_sync", [bad])
    first = await data_sync.sync(db, settings, sources=sources, log=lambda _m: None)
    assert _actions(first)["delta/a_bad.json"] == "failed"
    assert _actions(first)["delta/cinemas.json"] == "applied"  # one bad file does not stop the rest
    status = {i.key: i for i in (await data_sync.status(db, settings, sources=sources)).items}
    assert not status["delta/a_bad.json"].applied
    assert "activity.nope" in (status["delta/a_bad.json"].last_error or "")
    second = await data_sync.sync(db, settings, sources=sources, log=lambda _m: None)
    assert _actions(second)["delta/a_bad.json"] == "failed"
    assert _actions(second)["delta/cinemas.json"] == "skipped"


async def test_another_process_holding_the_lock_means_nothing_runs(
    empty_db: tuple[Database, Settings], sources: data_sync.Sources
) -> None:
    db, settings = empty_db
    with data_sync.file_lock(data_sync.lock_path(settings)) as got:
        assert got
        report = await data_sync.sync(db, settings, sources=sources, log=lambda _m: None)
    assert report.locked and report.results == []
    async with db.sessionmaker() as s:
        assert await s.scalar(select(func.count()).select_from(DataSync)) == 0
    after = await data_sync.sync(db, settings, sources=sources, log=lambda _m: None)
    assert not after.locked and _actions(after)["seed"] == "applied"


async def test_the_shipped_files_load_into_an_empty_database(empty_db: tuple[Database, Settings]) -> None:
    """The real seed, every real delta and the universities file — what the first production sync does."""
    db, settings = empty_db
    report = await data_sync.sync(db, settings, log=lambda _m: None)
    assert report.count("failed") == 0, [r.error for r in report.results if r.error]
    keys = set(_actions(report))
    assert {"seed", "delta/cinemas.json", "anchors/universities.json"} <= keys
    again = await data_sync.sync(db, settings, log=lambda _m: None)
    assert set(_actions(again).values()) == {"skipped"}


def test_runs_on_start_only_in_production_unless_told() -> None:
    base = {"_env_file": None, "jwt_secret": "x" * 40}
    assert not data_sync.enabled_on_start(Settings(**base, app_env="local"))
    assert not data_sync.enabled_on_start(Settings(**base, app_env="test"))
    assert data_sync.enabled_on_start(Settings(**base, app_env="production"))
    assert not data_sync.enabled_on_start(Settings(**base, app_env="production", data_sync_on_start=False))
    assert data_sync.enabled_on_start(Settings(**base, app_env="local", data_sync_on_start=True))


# --- admin API ------------------------------------------------------------------------------------------


async def test_admin_sees_the_state_and_can_start_it(
    client: httpx.AsyncClient,
    admin_headers: dict[str, str],
    user_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert (await client.get("/v1/admin/database/data-sync", headers=user_headers)).status_code == 403
    assert (await client.post("/v1/admin/database/data-sync", headers=user_headers)).status_code == 403

    r = await client.get("/v1/admin/database/data-sync", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    keys = {i["key"] for i in body["items"]}
    assert {"seed", "delta/cinemas.json", "anchors/universities.json"} <= keys
    assert body["running"] is False

    called: list[bool] = []

    async def fake_sync(*_a: object, **_k: object) -> None:  # the shared test DB keeps its fixtures
        called.append(True)

    monkeypatch.setattr(data_sync, "sync", fake_sync)
    started = await client.post("/v1/admin/database/data-sync", headers=admin_headers)
    assert started.status_code == 202
    await asyncio.sleep(0)
    assert called == [True]
