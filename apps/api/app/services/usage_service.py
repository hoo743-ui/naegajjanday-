"""Who came, day by day — logged in or not (docs/50).

First-party: page views from `visit` (a keyed hash of a browser's random id, no IP), accounts from `user`,
logins from `refresh_token`, courses from `recommendation_log`. Days are Korean calendar days.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.infra.db.base import as_utc
from app.infra.db.models import Course, OAuthAccount, RecommendationLog, RefreshToken, User, Visit
from app.schemas import admin as dto

MAX_ROWS = 200_000
COHORT_WEEKS = 8
SAVED = ("saved", "shared", "completed")


class UsageService:
    def __init__(self, session: AsyncSession, timezone: str = "Asia/Seoul") -> None:
        self._s = session
        self._tz = ZoneInfo(timezone)

    def _day(self, at: datetime) -> date:
        utc = as_utc(at)
        assert utc is not None
        return utc.astimezone(self._tz).date()

    def _bounds(self, first: date, last: date) -> tuple[datetime, datetime]:
        return (
            datetime.combine(first, time.min, tzinfo=self._tz),
            datetime.combine(last + timedelta(days=1), time.min, tzinfo=self._tz),
        )

    async def users(self, date_from: date, date_to: date) -> dto.UserAnalytics:
        # visits from 29 days before the range: MAU on its first day needs them
        start, end = self._bounds(date_from - timedelta(days=29), date_to)
        range_start = self._bounds(date_from, date_to)[0]
        visits = (
            await self._s.execute(
                select(Visit.visitor, Visit.user_id, Visit.referrer, Visit.device, Visit.created_at)
                .where(Visit.created_at >= start, Visit.created_at < end)
                .order_by(Visit.created_at)
                .limit(MAX_ROWS)
            )
        ).all()
        days = [date_from + timedelta(days=i) for i in range((date_to - date_from).days + 1)]
        seen: dict[date, set[str]] = defaultdict(set)
        known: dict[date, set[str]] = defaultdict(set)
        views: Counter[date] = Counter()
        first_ref: dict[str, str] = {}
        devices: Counter[str] = Counter()
        for visitor, user_id, referrer, device, at in visits:
            d = self._day(at)
            seen[d].add(visitor)
            if user_id is not None:
                known[d].add(visitor)
            if d >= date_from:
                views[d] += 1
                if visitor not in first_ref:
                    first_ref[visitor] = referrer or "직접 방문"
                    devices[device] += 1

        async def per_day(
            column: InstrumentedAttribute[datetime], *where: ColumnElement[bool]
        ) -> Counter[date]:
            s, e = self._bounds(date_from, date_to)
            rows = await self._s.scalars(
                select(column).where(column >= s, column < e, *where).limit(MAX_ROWS)
            )
            return Counter(self._day(at) for at in rows.all())

        signups = await per_day(User.created_at)
        logins = await per_day(RefreshToken.created_at)
        courses = await per_day(RecommendationLog.created_at)
        anon_courses = await per_day(RecommendationLog.created_at, RecommendationLog.user_id.is_(None))
        saved = await per_day(Course.created_at, Course.status.in_(SAVED))

        def window(last: date, n: int) -> set[str]:
            out: set[str] = set()
            for i in range(n):
                out |= seen.get(last - timedelta(days=i), set())
            return out

        daily = [
            dto.UsageDay(
                date=d,
                dau=len(seen[d]),
                visitors=len(seen[d]),
                logged_in=len(known[d]),
                anonymous=len(seen[d] - known[d]),
                page_views=views[d],
                new_users=signups[d],
                logins=logins[d],
                courses=courses[d],
                courses_anonymous=anon_courses[d],
                saved=saved[d],
            )
            for d in days
        ]
        mau = len(window(date_to, 30))
        avg_dau = sum(x.dau for x in daily) / max(1, len(daily))
        in_range = window(date_to, len(days))
        logged_range = set().union(*(known[d] for d in days)) if days else set()

        providers: Counter[str] = Counter()
        for provider, n in (
            await self._s.execute(select(OAuthAccount.provider, func.count()).group_by(OAuthAccount.provider))
        ).all():
            providers[str(provider)] += int(n)
        with_id = await self._s.scalar(
            select(func.count()).select_from(User).where(User.login_id.is_not(None))
        )
        if with_id:
            providers["아이디"] += int(with_id)

        return dto.UserAnalytics(
            range=dto.DateRangeOut(from_=date_from, to=date_to),
            totals=dto.UsageTotals(
                users=int(await self._s.scalar(select(func.count()).select_from(User)) or 0),
                dau=len(seen[date_to]),
                wau=len(window(date_to, 7)),
                mau=mau,
                new_users=sum(signups.values()),
                stickiness=round(avg_dau / mau, 3) if mau else 0.0,
                visitors=len(in_range),
                logged_in=len(logged_range),
                anonymous=len(in_range - logged_range),
                page_views=sum(views.values()),
                courses=sum(courses.values()),
                courses_anonymous=sum(anon_courses.values()),
            ),
            daily=daily,
            acquisition=[
                dto.ChannelCount(channel=c, users=n) for c, n in Counter(first_ref.values()).most_common(10)
            ],
            providers=[dto.ProviderCount(provider=p, users=n) for p, n in providers.most_common()],
            devices=[dto.DeviceCount(device=k, users=n) for k, n in devices.most_common()],
            cohorts=self._cohorts(visits, range_start),
        )

    def _cohorts(self, visits: Sequence[Any], range_start: datetime) -> list[dto.Cohort]:
        """Weekly: of the browsers first seen in a week, the share that came back N weeks later."""
        first: dict[str, date] = {}
        weeks: dict[str, set[date]] = defaultdict(set)
        for visitor, _user, _ref, _device, at in visits:
            if (as_utc(at) or range_start) < range_start:
                continue
            d = self._day(at)
            monday = d - timedelta(days=d.weekday())
            first.setdefault(visitor, monday)
            weeks[visitor].add(monday)
        by_week: dict[date, list[str]] = defaultdict(list)
        for visitor, monday in first.items():
            by_week[monday].append(visitor)
        out = []
        for monday in sorted(by_week)[-COHORT_WEEKS:]:
            members = by_week[monday]
            retention = []
            for i in range(COHORT_WEEKS):
                week = monday + timedelta(weeks=i)
                if week > max(first.values()):
                    break
                retention.append(round(sum(1 for v in members if week in weeks[v]) / len(members), 3))
            out.append(dto.Cohort(cohort=monday.isoformat(), size=len(members), retention=retention))
        return out
