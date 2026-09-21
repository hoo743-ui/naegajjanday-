from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.db.models import Course, CourseFeedback, RecommendationLog

OWNED_STATUSES = ("saved", "shared", "completed")


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
        stmt = select(Course).where(Course.recommendation_log_id == course.recommendation_log_id)
        return list((await self._s.scalars(stmt.order_by(Course.id))).all())

    async def list_for_user(self, user_id: int, cursor: int | None, limit: int) -> list[Course]:
        stmt = select(Course).where(Course.user_id == user_id, Course.status.in_(OWNED_STATUSES))
        if cursor is not None:
            stmt = stmt.where(Course.id < cursor)
        return list((await self._s.scalars(stmt.order_by(Course.id.desc()).limit(limit))).all())

    async def delete(self, course: Course) -> None:
        await self._s.delete(course)

    async def add_feedback(self, feedback: CourseFeedback) -> None:
        self._s.add(feedback)
        await self._s.flush()
