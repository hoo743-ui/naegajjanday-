"""TourAPI opening hours, a little every day, inside the API process (backlog 10, docs/55).

`ingest-bulk tourapi-hours --limit 800` has to run once a day on the production database: one call per
place against a key shared by the site and capped at 1,000 calls a day, so the ~16,000 places are worked
through over weeks. A Render Cron Job cannot reach the web service's disk (the SQLite file), and a GitHub
Actions schedule would need an admin credential in GitHub — so the API runs it itself:

- once a day at `TOURAPI_HOURS_DAILY_AT` (KST, default 04:30 — after the quota resets at midnight,
  before people plan their day); after a deploy or restart past that time, the day's run happens right
  away if it has not happened yet (a restart never runs it twice: the day is recorded in `data_sync`,
  key `@tourapi-hours`);
- never more than `TOURAPI_HOURS_DAILY_LIMIT` (800) calls, and never past what the quota hook (docs/47)
  says is left minus the reserve for the site's own lookups — `tourapi_hours.run` already stops there;
- no key (`TOURAPI_SERVICE_KEY` empty) → it logs once and does nothing; off outside production unless
  `TOURAPI_HOURS_DAILY=true`; `TOURAPI_HOURS_DAILY=false` turns it off in production;
- one process at a time: a file lock next to the database, like data sync.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from app.core.config import Settings
from app.core.logging import get_logger
from app.infra.db.base import utcnow
from app.infra.db.models import DataSync
from app.infra.db.session import Database
from app.services import data_sync

logger = get_logger(__name__)

JOB_KEY = "@tourapi-hours"  # the data_sync row that remembers the last day it ran
Clock = Callable[[], datetime]
Sleep = Callable[[float], Awaitable[None]]


def enabled(settings: Settings) -> bool:
    return settings.is_production if settings.tourapi_hours_daily is None else settings.tourapi_hours_daily


def run_at(settings: Settings) -> time:
    hh, mm = settings.tourapi_hours_daily_at.split(":")
    return time(int(hh), int(mm))


def lock_path(settings: Settings) -> Path:
    base = data_sync.lock_path(settings)
    return base.with_name(base.name.replace("data-sync", "tourapi-hours"))


async def last_day(db: Database, tz: ZoneInfo) -> str | None:
    """The KST day of the last run (attempted, whatever its result)."""
    async with db.sessionmaker() as session:
        row = await session.get(DataSync, JOB_KEY)
    if row is None or row.attempted_at is None:
        return None
    at = row.attempted_at if row.attempted_at.tzinfo else row.attempted_at.replace(tzinfo=ZoneInfo("UTC"))
    return at.astimezone(tz).date().isoformat()


def seconds_until_due(now: datetime, at: time, done_today: bool) -> float:
    """0 when today's run is due (past the hour, not done yet), else the wait until the next one."""
    due = now.replace(hour=at.hour, minute=at.minute, second=0, microsecond=0)
    if now >= due and not done_today:
        return 0.0
    if now >= due:
        due += timedelta(days=1)
    return (due - now).total_seconds()


async def run_once(db: Database, settings: Settings, *, tz: ZoneInfo | None = None) -> str:
    """Today's batch, unless it already ran today. Returns a one-line summary (also stored)."""
    from app.infra.ingestion.bulk import tourapi_hours

    tz = tz or ZoneInfo(settings.timezone)
    await data_sync._ensure_table(db)
    today = datetime.now(tz).date().isoformat()
    if await last_day(db, tz) == today:
        return "already ran today"
    with data_sync.file_lock(lock_path(settings)) as got:
        if not got:
            return "another process is running it"
        await data_sync._record(db, JOB_KEY, attempted_at=utcnow())
        try:
            report = await tourapi_hours.run(
                db,
                settings.tourapi_service_key,
                limit=settings.tourapi_hours_daily_limit,
                log=lambda m: logger.info("tourapi_hours_daily.log", message=m),
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"[:2000]
            await data_sync._record(db, JOB_KEY, last_error=error)
            raise
        summary = report.line()
        await data_sync._record(db, JOB_KEY, applied_at=utcnow(), summary=summary, last_error=None)
        return summary


async def run_forever(
    db: Database,
    settings: Settings,
    *,
    clock: Clock | None = None,
    sleep: Sleep = asyncio.sleep,
    max_runs: int | None = None,
) -> None:
    """The startup task. Never crashes the app: a failed day is logged and tried again the next day."""
    if not settings.tourapi_service_key:
        logger.info("tourapi_hours_daily.off", reason="TOURAPI_SERVICE_KEY is not set")
        return
    tz = ZoneInfo(settings.timezone)
    now_ = clock or (lambda: datetime.now(tz))
    at = run_at(settings)
    runs = 0
    await sleep(settings.data_sync_delay_s + 60)  # after data sync has started; the health check first
    while max_runs is None or runs < max_runs:
        try:
            await data_sync._ensure_table(db)
            done_today = await last_day(db, tz) == now_().date().isoformat()
        except Exception:
            logger.exception("tourapi_hours_daily.state_failed")
            done_today = True
        wait = seconds_until_due(now_(), at, done_today)
        if wait > 0:
            await sleep(min(wait, 6 * 3600))  # wake up now and then: the clock may have jumped
            continue
        runs += 1
        try:
            result = await run_once(db, settings, tz=tz)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("tourapi_hours_daily.failed")
            continue
        logger.info("tourapi_hours_daily.done", result=result)
