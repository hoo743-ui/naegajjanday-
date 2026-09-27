"""Quota guard (docs/47 · docs/63): a bulk job asks before each batch, stops cleanly, says where, falls back."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.config import Settings
from app.infra import api_usage, quota_guard
from app.infra.db.models import ApiUsage, IngestionJob, Region
from app.infra.db.session import Database
from app.infra.ingestion import pipeline
from app.infra.ingestion.bulk import tourapi_bulk
from app.infra.quota_guard import QuotaGuard


def quiet(_m: str) -> None:
    return None


def test_a_batch_that_would_eat_the_reserve_stops_the_job() -> None:
    lines: list[str] = []
    g = QuotaGuard("tourapi", left=10, reserve=3, job="t", log=lines.append)
    assert g.allows(5) and g.budget(100) == 7
    g.spent(5)
    assert g.remaining == 5
    assert not g.allows(3, cursor={"page": 4})  # 5 − 3 = 2 < reserve 3
    assert g.stopped is not None and g.stopped.cursor == {"page": 4}
    assert lines[-1].startswith("quota.stop provider=tourapi remaining=5 reserve=3 job=t")
    assert not g.allows(1)  # once stopped, stays stopped


def test_an_unknown_limit_is_counted_not_blocked() -> None:
    g = QuotaGuard("kopis", left=None, reserve=0, log=quiet)
    assert g.allows(10_000) and g.budget(50) == 50 and g.remaining is None


def test_the_providers_own_counter_wins_and_an_exhausted_quota_stops() -> None:
    g = QuotaGuard("tourapi", left=500, reserve=100, log=quiet)
    g.spent(1, remaining=101)  # the header says 101 left, whatever we counted
    assert g.remaining == 101 and not g.allows(2)
    h = QuotaGuard("tourapi", left=500, reserve=100, log=quiet)
    h.exhausted(cursor="c9")
    assert h.remaining == 0 and h.stopped is not None and h.stopped.cursor == "c9"


def test_reserve_comes_from_quotas_json() -> None:
    assert quota_guard.reserve_of("tourapi") == 100
    assert quota_guard.reserve_of("kakao_local") == 1000
    assert quota_guard.reserve_of("nobody") == 0


@pytest_asyncio.fixture
async def db(tmp_path: Path) -> AsyncIterator[Database]:
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        app_env="test",
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'quota.db').as_posix()}",
    )
    database = Database(settings)
    await database.create_all()
    yield database
    await database.dispose()


async def test_what_is_left_and_where_it_stopped(db: Database) -> None:
    async with db.sessionmaker() as session:
        session.add(ApiUsage(provider="tourapi", day=api_usage.today(), calls=880, errors=0))
        await session.commit()
        guard = await quota_guard.open_guard(session, "tourapi", job="tourapi-hours", log=quiet)
        assert guard.left == 120 and guard.reserve == 100
        assert guard.allows(20, cursor="a") and not guard.allows(21, cursor="b")
        await quota_guard.record_stop(session, guard, fallback="default hours")
        row = (await session.scalars(select(IngestionJob))).one()
        assert row.status == "deferred" and row.provider == "tourapi" and "quota.stop" in (row.error or "")
        cursor = await quota_guard.last_stop(session, "tourapi-hours")
        assert cursor is not None and cursor["cursor"] == "b" and cursor["remaining"] == 120
        assert await quota_guard.last_stop(session, "universities-kakao") is None


async def test_a_monthly_quota_counts_the_whole_month(db: Database) -> None:
    today = api_usage.today()
    async with db.sessionmaker() as session:
        session.add(ApiUsage(provider="pexels", day=today, calls=100, errors=0))
        if today[6:] != "01":
            session.add(ApiUsage(provider="pexels", day=today[:6] + "01", calls=24_000, errors=0))
        await session.commit()
        left = await quota_guard.quota_left(session, "pexels")
    assert left == (25_000 - 100 - (0 if today[6:] == "01" else 24_000))


async def test_an_exhausted_day_is_zero(db: Database) -> None:
    async with db.sessionmaker() as session:
        session.add(
            ApiUsage(
                provider="data_go_kr",
                day=api_usage.today(),
                calls=3,
                errors=1,
                exhausted_at=pipeline.utcnow(),
            )
        )
        await session.commit()
        assert await quota_guard.quota_left(session, "data_go_kr") == 0


def test_tourapi_pull_keeps_the_cached_pages_when_the_quota_stops(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "14_1.json").write_text(json.dumps([{"contentid": "old"}]), "utf-8")
    asked: list[tuple[str, str]] = []

    def fake_get(
        _client: Any, _key: str, op: str, params: dict[str, str]
    ) -> tuple[list[dict[str, Any]], int]:
        asked.append((params.get("contentTypeId", op), params["pageNo"]))
        return [{"contentid": "new"}], 1

    monkeypatch.setattr(tourapi_bulk, "_get", fake_get)
    monkeypatch.setattr(tourapi_bulk, "CALL_GAP_S", 0)
    guard = QuotaGuard("tourapi", left=1, reserve=0, job="tourapi-bulk", log=quiet)
    counts = tourapi_bulk.download(
        "k", tmp_path, {"12": "관광지", "14": "문화시설"}, date(2026, 9, 1), force=True, guard=guard
    )
    assert asked == [("12", "1")]  # one call was all the quota allowed
    assert guard.stopped is not None and guard.stopped.cursor == {"kind": "14", "page": 1}
    assert json.loads((tmp_path / "14_1.json").read_text("utf-8")) == [{"contentid": "old"}]  # fallback kept
    assert counts == {"12": 1, "14": 1, "festival": 0}


class _NoCalls:
    name = "tourapi"

    async def fetch(self, *_a: Any, **_k: Any) -> AsyncIterator[Any]:
        raise AssertionError("a deferred job must not call out")
        yield  # pragma: no cover


async def test_a_region_pull_waits_when_the_quota_is_near(db: Database) -> None:
    async with db.sessionmaker() as session:
        session.add(ApiUsage(provider="tourapi", day=api_usage.today(), calls=950, errors=0))
        await session.commit()
        job = IngestionJob(provider="tourapi", cursor={"page": 7}, params={})
        region = Region(
            slug="seoul-seongsu", name="성수", level=3, center_lat=37.5, center_lng=127.0, radius_m=900
        )
        report = await pipeline.IngestionPipeline(session, []).run(_NoCalls(), region, job)  # type: ignore[arg-type]
    assert job.status == "deferred" and job.cursor == {"page": 7}  # resumes from the same page
    assert report.fetched == 0 and "quota.stop provider=tourapi" in report.errors[0]
