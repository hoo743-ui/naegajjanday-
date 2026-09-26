from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.db.models import Course, CourseFeedback, CourseStop, RecommendationLog

OWNED_STATUSES = ("saved", "shared", "completed")
REPLACED = "replaced"  # a day of a trip that was planned again: the new course took its place


class SqlCourseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, course: Course) -> Course:
        self._s.add(course)
        await self._s.flush()
        return course

    async def add_log(self, log: RecommendationLog) -> RecommendationLog:
        self._s.add(log)
        await self._s.flush()
        return log

    async def get_by_public_id(self, public_id: str) -> Course | None:
        return await self._s.scalar(select(Course).where(Course.public_id == public_id))

    async def siblings(self, course: Course) -> list[Course]:
        """Courses produced by the same generate call, in the order they were offered."""
        if course.recommendation_log_id is None:
            return [course]
        stmt = select(Course).where(
            Course.recommendation_log_id == course.recommendation_log_id, Course.status != REPLACED
        )
        rows = list((await self._s.scalars(stmt.order_by(Course.id))).all())
        # a day planned again has a newer id than the days after it: the day number decides
        return sorted(rows, key=lambda c: ((c.request or {}).get("day") or 0, c.id))

    async def history_in(
        self, user_id: int, region_ids: Sequence[int], since: datetime
    ) -> tuple[list[datetime], list[str], list[int]]:
        """What this user planned around here since then (처음 · 자주, recommendation.familiarity):
        when (each generate · each saved or visited course's day), the places the app showed them (public ids,
        from the recommendation log — it outlives unsaved courses), and the places of their own courses
        (ids — a stop swapped after the fact is only there). Newest first."""
        if not region_ids:
            return [], [], []
        logs = (
            await self._s.execute(
                select(RecommendationLog.created_at, RecommendationLog.selected_courses)
                .where(
                    RecommendationLog.user_id == user_id,
                    RecommendationLog.region_id.in_(region_ids),
                    RecommendationLog.created_at >= since,
                )
                .order_by(RecommendationLog.id.desc())
            )
        ).all()
        owned = (
            await self._s.execute(
                select(Course.id, Course.start_at)
                .where(
                    Course.user_id == user_id,
                    Course.region_id.in_(region_ids),
                    Course.status.in_(OWNED_STATUSES),
                    Course.created_at >= since,
                )
                .order_by(Course.id.desc())
            )
        ).all()
        when = [at for at, _ in logs] + [at for _, at in owned]
        shown = [str(pid) for _, got in logs for c in got or [] for pid in (c or {}).get("places") or []]
        places: list[int] = []
        if owned:
            rows = await self._s.execute(
                select(CourseStop.place_id)
                .where(CourseStop.course_id.in_([cid for cid, _ in owned]), CourseStop.place_id.is_not(None))
                .order_by(CourseStop.course_id.desc(), CourseStop.position)
            )
            places = [int(pid) for (pid,) in rows.all()]
        return when, shown, places

    async def list_for_user(self, user_id: int, cursor: int | None, limit: int) -> list[Course]:
        stmt = select(Course).where(Course.user_id == user_id, Course.status.in_(OWNED_STATUSES))
        if cursor is not None:
            stmt = stmt.where(Course.id < cursor)
        return list((await self._s.scalars(stmt.order_by(Course.id.desc()).limit(limit))).all())

    async def delete(self, course: Course) -> None:
        await self._s.delete(course)

    # --- retention: never-saved courses live for `unsaved_course_ttl_hours` ---------------------

    async def count_expired_unsaved(self, cutoff: datetime) -> int:
        stmt = select(func.count(Course.id)).where(
            Course.status.notin_(OWNED_STATUSES), Course.created_at < cutoff
        )
        return int(await self._s.scalar(stmt) or 0)

    async def expired_unsaved_ids(self, cutoff: datetime, limit: int) -> list[int]:
        stmt = select(Course.id).where(Course.status.notin_(OWNED_STATUSES), Course.created_at < cutoff)
        return list((await self._s.scalars(stmt.order_by(Course.id).limit(limit))).all())

    async def delete_unsaved_by_ids(self, ids: Sequence[int]) -> int:
        """One atomic statement; stops and feedback go with the row (`ON DELETE CASCADE`).

        The status guard is repeated on purpose: a course saved after it was selected must survive.
        """
        if not ids:
            return 0
        result = await self._s.execute(
            delete(Course).where(Course.id.in_(ids), Course.status.notin_(OWNED_STATUSES))
        )
        return int(getattr(result, "rowcount", 0) or 0)

    async def add_feedback(self, feedback: CourseFeedback) -> None:
        self._s.add(feedback)
        await self._s.flush()
