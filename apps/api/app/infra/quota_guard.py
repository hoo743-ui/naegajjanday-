"""Stop a bulk job before it eats a quota the running site still needs (창업자 2026-09-26, docs/47 · docs/63).

The quota hook (`api_usage`) counts every call after it is made. A bulk path (ingestion, enrichment, the daily
hours job) must also ask **before** each batch: "if I make these calls, is there still `reserve` left for the
site?" When the projected use would pass `limit − reserve`, the job stops cleanly — never half-way through a
write — logs `quota.stop provider=… remaining=…`, and writes where it stopped (an `ingestion_job` row,
status `deferred`, the resume cursor in `cursor`). Then it falls back instead of failing:

1. data already on disk (the SEMAS · 인허가 files, TourAPI pages cached under raw/, answers shipped in
   data/bulk/delta — `--from-file`),
2. answers already stored (the course keeps its estimated hours · addresses),
3. the rest waits for tomorrow's run (the daily job starts from the cursor / the queue order).

`QuotaGuard` itself holds no DB: `open_guard` reads what is left, the job asks `allows()` before a batch and
tells `spent()` after, and `record_stop` writes the cursor. A sync path (tourapi_bulk uses `httpx.Client`,
which the hook does not see) uses the same object — its `spent()` is the only count there is.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infra import api_usage

logger = get_logger(__name__)

Log = Callable[[str], None]
DEFAULT_RESERVE = {"tourapi": 100, "data_go_kr": 50, "kakao_local": 1000, "naver_search": 500}
STOP_STATUS = "deferred"
STOP_JOB_TYPE = "quota"


@dataclass(slots=True)
class QuotaStop:
    provider: str
    job: str
    remaining: int | None
    reserve: int
    cursor: Any
    reason: str

    def line(self) -> str:
        return (
            f"quota.stop provider={self.provider} remaining={self.remaining} reserve={self.reserve} "
            f"job={self.job} cursor={self.cursor}"
        )


@dataclass(slots=True)
class QuotaGuard:
    provider: str
    left: int | None  # calls left in the quota period when the job started (None: the limit is unknown)
    reserve: int
    job: str = ""
    used: int = 0  # calls this job made
    stopped: QuotaStop | None = None
    log: Log = field(default=print)

    @property
    def remaining(self) -> int | None:
        return None if self.left is None else max(0, self.left - self.used)

    def allows(self, calls: int = 1, *, cursor: Any = None) -> bool:
        """Before a batch of `calls`: False (and stopped) when they would eat into the reserve."""
        if self.stopped is not None:
            return False
        left = self.remaining
        if left is None or calls <= left - self.reserve:
            return True
        self._stop(cursor, f"{calls} more calls would leave {left - calls} (< reserve {self.reserve})")
        return False

    def budget(self, wanted: int) -> int:
        """How many of `wanted` calls may go out now (0 when none)."""
        left = self.remaining
        return wanted if left is None else max(0, min(wanted, left - self.reserve))

    def spent(self, calls: int = 1, *, remaining: int | None = None) -> None:
        """After calls went out. A provider's own counter (rate-limit header) is more exact than ours."""
        self.used += calls
        if remaining is not None:
            self.left, self.used = remaining, 0

    def exhausted(self, *, cursor: Any = None) -> None:
        """The provider said the quota is gone (HTTP 429, data.go.kr code 22)."""
        self.left, self.used = 0, 0
        if self.stopped is None:
            self._stop(cursor, "the provider says today's quota is used up")

    def _stop(self, cursor: Any, reason: str) -> None:
        self.stopped = QuotaStop(self.provider, self.job, self.remaining, self.reserve, cursor, reason)
        logger.warning(
            "quota.stop",
            provider=self.provider,
            remaining=self.remaining,
            reserve=self.reserve,
            job=self.job,
            cursor=str(cursor),
            reason=reason,
        )
        self.log(self.stopped.line())


def reserve_of(provider: str, spec: Mapping[str, Any] | None = None) -> int:
    """data/quotas.json › <provider>.reserve, else the default for the provider (0 if unknown)."""
    spec = api_usage.quotas().get(provider, {}) if spec is None else spec
    if spec.get("reserve") is not None:
        return int(spec["reserve"])
    return DEFAULT_RESERVE.get(provider, 0)


async def quota_left(session: AsyncSession, provider: str) -> int | None:
    """Calls left of `provider`'s quota in its period (day or month, Asia/Seoul); None = unknown limit."""
    from app.infra.db.models import ApiUsage

    spec = api_usage.quotas().get(provider, {})
    day = api_usage.today()
    today_row = await session.get(ApiUsage, (provider, day))
    limit = (today_row.limit if today_row and today_row.limit else None) or spec.get("limit")
    if today_row and today_row.exhausted_at:
        return 0
    if not limit:
        return None
    if spec.get("period") == "month":
        rows = (
            await session.scalars(
                select(ApiUsage).where(ApiUsage.provider == provider, ApiUsage.day >= day[:6] + "01")
            )
        ).all()
        used = sum(r.calls for r in rows)
    else:
        used = today_row.calls if today_row else 0
    if today_row and today_row.remaining is not None:
        used = max(used, int(limit) - today_row.remaining)
    return max(0, int(limit) - used)


async def open_guard(
    session: AsyncSession, provider: str, *, job: str, reserve: int | None = None, log: Log = print
) -> QuotaGuard:
    left = await quota_left(session, provider)
    guard = QuotaGuard(provider, left, reserve_of(provider) if reserve is None else reserve, job=job, log=log)
    log(f"quota provider={provider} left={left} reserve={guard.reserve} job={job}")
    return guard


def resume_after() -> datetime:
    """The quota resets at midnight Asia/Seoul: a deferred job resumes from then."""
    now = datetime.now(api_usage.KST)
    return (now + timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0)


async def record_stop(session: AsyncSession, guard: QuotaGuard, *, fallback: str = "") -> None:
    """Where the job stopped: an `ingestion_job` row (status deferred, the cursor to resume from)."""
    from app.infra.db.base import utcnow
    from app.infra.db.models import IngestionJob

    stop = guard.stopped
    if stop is None:
        return
    session.add(
        IngestionJob(
            provider=stop.provider,
            job_type=STOP_JOB_TYPE,
            status=STOP_STATUS,
            cursor={
                "job": stop.job,
                "cursor": stop.cursor,
                "remaining": stop.remaining,
                "reserve": stop.reserve,
                "used": guard.used,
                "resume_after": resume_after().isoformat(),
            },
            params={"job": stop.job, "fallback": fallback},
            error=f"{stop.line()} — {stop.reason}",
            finished_at=utcnow(),
        )
    )
    await session.commit()


async def last_stop(session: AsyncSession, job: str) -> dict[str, Any] | None:
    """The cursor of the last time `job` stopped for the quota (None: it never did)."""
    from app.infra.db.models import IngestionJob

    rows = (
        await session.scalars(
            select(IngestionJob)
            .where(IngestionJob.job_type == STOP_JOB_TYPE, IngestionJob.status == STOP_STATUS)
            .order_by(IngestionJob.id.desc())
            .limit(50)
        )
    ).all()
    row = next((r for r in rows if (r.cursor or {}).get("job") == job), None)
    return dict(row.cursor or {}) if row is not None else None
