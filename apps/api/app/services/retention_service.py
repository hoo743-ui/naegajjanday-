"""Retention batches: what the product promises about deleting data, actually enforced.

* a course nobody saved disappears `unsaved_course_ttl_hours` after it was generated
* an account whose owner asked for deletion is hard-purged `account_purge_grace_days` later

Both run from Celery beat (`app.workers.tasks`) and from cron via `python -m app.cli purge-*`.
Only counts are logged — never e-mails, nicknames, course contents or ids of people.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.logging import get_logger
from app.infra.db.base import as_utc, utcnow
from app.infra.db.models import (
    AuditLog,
    ChatSession,
    Course,
    CourseFeedback,
    OAuthAccount,
    PlaceRevision,
    RecommendationLog,
    RefreshToken,
    User,
    UserPreference,
    Visit,
)
from app.infra.db.session import Database
from app.repositories.course_repo import SqlCourseRepository
from app.repositories.user_repo import SqlUserRepository

logger = get_logger(__name__)

COURSE_BATCH = 500
ACCOUNT_BATCH = 50
# request fields of a recommendation log that can point at a person once the account is gone
LOG_PERSONAL_KEYS = ("origin", "origin_label")


@dataclass(frozen=True, slots=True)
class CoursePurgeReport:
    matched: int
    deleted: int
    dry_run: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class AccountPurgeReport:
    matched: int
    accounts: int = 0
    courses: int = 0
    logs_anonymized: int = 0
    dry_run: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _rowcount(result: Any) -> int:
    return max(0, int(getattr(result, "rowcount", 0) or 0))


# --- never-saved courses ---------------------------------------------------------------------


async def purge_unsaved_courses(
    db: Database, settings: Settings, *, dry_run: bool = False, now: datetime | None = None
) -> CoursePurgeReport:
    """Removes courses (with their stops) that were never saved and are older than the TTL.

    Saved / shared / completed courses are never touched; their unsaved alternatives from the same
    generate call are — the detail endpoint simply lists the siblings that still exist.
    """
    cutoff = (now or utcnow()) - timedelta(hours=settings.unsaved_course_ttl_hours)
    async with db.sessionmaker() as session:
        courses = SqlCourseRepository(session)
        matched = await courses.count_expired_unsaved(cutoff)
        deleted = 0
        if not dry_run:
            while ids := await courses.expired_unsaved_ids(cutoff, COURSE_BATCH):
                removed = await courses.delete_unsaved_by_ids(ids)
                await session.commit()
                deleted += removed
                if removed == 0:  # everything selected was saved in the meantime: do not spin
                    break
    report = CoursePurgeReport(matched=matched, deleted=deleted, dry_run=dry_run)
    logger.info("retention.courses_purged", ttl_hours=settings.unsaved_course_ttl_hours, **report.as_dict())
    return report


# --- accounts --------------------------------------------------------------------------------


def purge_due_at(user: User, settings: Settings) -> datetime | None:
    requested = as_utc(user.delete_requested_at)
    if user.status != "deleting" or requested is None:
        return None
    return requested + timedelta(days=settings.account_purge_grace_days)


def is_purge_due(user: User, settings: Settings, now: datetime | None = None) -> bool:
    due = purge_due_at(user, settings)
    return due is not None and due <= (now or utcnow())


async def purge_user(session: AsyncSession, user: User) -> tuple[int, int]:
    """Hard-deletes one account and everything personal. Returns `(courses, anonymized logs)`.

    Deleted: OAuth links, refresh tokens, preferences, every course the user owns (stops and
    feedback included), feedback left on other courses, chat sessions with their messages.
    Anonymized and kept: recommendation logs (aggregate statistics) and admin audit trails.
    The caller commits.
    """
    uid = user.id
    courses = _rowcount(await session.execute(delete(Course).where(Course.user_id == uid)))
    await session.execute(delete(CourseFeedback).where(CourseFeedback.user_id == uid))
    await session.execute(delete(ChatSession).where(ChatSession.user_id == uid))
    await session.execute(delete(OAuthAccount).where(OAuthAccount.user_id == uid))
    await session.execute(delete(RefreshToken).where(RefreshToken.user_id == uid))
    await session.execute(delete(UserPreference).where(UserPreference.user_id == uid))

    logs = (await session.scalars(select(RecommendationLog).where(RecommendationLog.user_id == uid))).all()
    for log in logs:
        log.user_id = None
        log.request = {k: v for k, v in (log.request or {}).items() if k not in LOG_PERSONAL_KEYS}
    await session.execute(update(PlaceRevision).where(PlaceRevision.admin_id == uid).values(admin_id=None))
    await session.execute(
        update(AuditLog).where(AuditLog.actor_id == uid).values(actor_id=None, ip=None, user_agent=None)
    )
    await session.flush()
    await session.delete(user)
    await session.flush()
    return courses, len(logs)


async def purge_deleted_accounts(
    db: Database, settings: Settings, *, dry_run: bool = False, now: datetime | None = None
) -> AccountPurgeReport:
    """Hard-purges accounts whose grace period is over. A login during the grace period cancels it."""
    cutoff = (now or utcnow()) - timedelta(days=settings.account_purge_grace_days)
    async with db.sessionmaker() as session:
        users = SqlUserRepository(session)
        if dry_run:
            due = await users.due_for_purge(cutoff)
            owned = await session.scalar(
                select(func.count(Course.id)).where(Course.user_id.in_([u.id for u in due]))
            )
            report = AccountPurgeReport(matched=len(due), courses=int(owned or 0), dry_run=True)
        else:
            matched = accounts = courses = anonymized = 0
            while batch := await users.due_for_purge(cutoff, ACCOUNT_BATCH):
                matched += len(batch)
                for user in batch:
                    removed, logs = await purge_user(session, user)
                    await session.commit()  # one account per transaction: a failure keeps the rest
                    accounts, courses, anonymized = accounts + 1, courses + removed, anonymized + logs
            report = AccountPurgeReport(
                matched=matched, accounts=accounts, courses=courses, logs_anonymized=anonymized
            )
    logger.info("retention.accounts_purged", grace_days=settings.account_purge_grace_days, **report.as_dict())
    return report


async def purge_old_visits(db: Database, settings: Settings, *, now: datetime | None = None) -> int:
    """Page views (docs/50) older than `visit_retention_days`. Never fails the caller: start-up goes on."""
    cutoff = (now or utcnow()) - timedelta(days=settings.visit_retention_days)
    try:
        async with db.session() as session:
            result = await session.execute(delete(Visit).where(Visit.created_at < cutoff))
            deleted = _rowcount(result)
    except Exception:
        logger.exception("retention.visits_purge_failed")
        return 0
    if deleted:
        logger.info("retention.visits_purged", retention_days=settings.visit_retention_days, deleted=deleted)
    return deleted


async def clear_old_ips(db: Database, settings: Settings, *, now: datetime | None = None) -> int:
    """IPs on page views and course requests are for spotting abuse: gone after `ip_retention_days`."""
    cutoff = (now or utcnow()) - timedelta(days=settings.ip_retention_days)
    cleared = 0
    try:
        async with db.session() as session:
            for model in (Visit, RecommendationLog):
                result = await session.execute(
                    update(model).where(model.created_at < cutoff, model.ip.is_not(None)).values(ip=None)
                )
                cleared += _rowcount(result)
    except Exception:
        logger.exception("retention.ip_clear_failed")
        return 0
    if cleared:
        logger.info("retention.ips_cleared", retention_days=settings.ip_retention_days, cleared=cleared)
    return cleared
