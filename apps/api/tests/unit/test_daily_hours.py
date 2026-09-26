"""Backlog 10: TourAPI opening hours once a day inside the API (docs/55) — when, how often, and never without a key."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio

from app.core.config import Settings
from app.infra.db.session import Database
from app.infra.ingestion.bulk import tourapi_hours
from app.services import daily_hours

KST = ZoneInfo("Asia/Seoul")


def _settings(tmp_path: Path, **kw: object) -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        app_env="test",
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'daily.db').as_posix()}",
        data_sync_delay_s=0,
        **kw,  # type: ignore[arg-type]
    )


@pytest_asyncio.fixture
async def db(tmp_path: Path) -> AsyncIterator[Database]:
    database = Database(_settings(tmp_path))
    await database.create_all()
    try:
        yield database
    finally:
        await database.dispose()


def test_due_after_the_hour_once_a_day() -> None:
    at = time(4, 30)
    before = datetime(2026, 9, 27, 3, 30, tzinfo=KST)
    assert daily_hours.seconds_until_due(before, at, done_today=False) == 3600
    after = datetime(2026, 9, 27, 13, 0, tzinfo=KST)  # a deploy at 13:00: today's run has not happened yet
    assert daily_hours.seconds_until_due(after, at, done_today=False) == 0
    assert daily_hours.seconds_until_due(after, at, done_today=True) == 15.5 * 3600  # tomorrow 04:30


def test_on_in_production_only_unless_told(tmp_path: Path) -> None:
    assert not daily_hours.enabled(_settings(tmp_path))
    assert daily_hours.enabled(_settings(tmp_path, tourapi_hours_daily=True))
    prod = Settings(_env_file=None, app_env="production", jwt_secret="x" * 40)  # type: ignore[call-arg]
    assert daily_hours.enabled(prod)
    off = Settings(_env_file=None, app_env="production", jwt_secret="x" * 40, tourapi_hours_daily=False)  # type: ignore[call-arg]
    assert not daily_hours.enabled(off)


async def test_no_key_means_nothing_happens(db: Database, tmp_path: Path) -> None:
    slept: list[float] = []

    async def sleep(s: float) -> None:
        slept.append(s)

    await daily_hours.run_forever(db, _settings(tmp_path, tourapi_service_key=None), sleep=sleep)
    assert slept == []  # returned at once: no loop, no calls


async def test_runs_once_a_day_with_the_limit(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str | None, int]] = []

    async def fake_run(
        _db: Database, key: str | None, *, limit: int, **_kw: object
    ) -> tourapi_hours.HoursReport:
        calls.append((key, limit))
        return tourapi_hours.HoursReport(calls=limit, parsed=3)

    monkeypatch.setattr(tourapi_hours, "run", fake_run)
    settings = _settings(tmp_path, tourapi_service_key="k", tourapi_hours_daily_limit=800)
    first = await daily_hours.run_once(db, settings)
    assert "parsed=3" in first
    assert await daily_hours.run_once(db, settings) == "already ran today"  # a restart does not run it twice
    assert calls == [("k", 800)]


async def test_the_loop_runs_when_due_and_survives_a_failure(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def failing_run(*_a: object, **_kw: object) -> tourapi_hours.HoursReport:
        raise tourapi_hours.HoursIngestError("TourAPI down")

    monkeypatch.setattr(tourapi_hours, "run", failing_run)
    slept: list[float] = []

    async def sleep(s: float) -> None:
        slept.append(s)

    noon = datetime(2026, 9, 27, 12, 0, tzinfo=KST)
    settings = _settings(tmp_path, tourapi_service_key="k")
    await daily_hours.run_forever(db, settings, clock=lambda: noon, sleep=sleep, max_runs=1)
    # the failed day is recorded as tried → the next wake-up waits for tomorrow, no retry storm
    assert await daily_hours.last_day(db, KST) == datetime.now(KST).date().isoformat()
