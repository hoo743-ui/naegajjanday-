"""`/admin/members` · `/admin/visits` · `/admin/course-requests` — who is here, what they asked (docs/50).

Operators only (the admin router checks the role). IPs are shown for spotting abuse and are cleared after
`ip_retention_days`; the privacy page says so.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select

from app.core.deps import SessionDep
from app.infra.db.models import (
    Course,
    OAuthAccount,
    Place,
    Purpose,
    RecommendationLog,
    RefreshToken,
    Region,
    User,
    Visit,
)

router = APIRouter(tags=["admin:people"])

Who = Literal["all", "member", "anonymous"]
SAVED = ("saved", "shared", "completed")


class UserRef(BaseModel):
    id: str
    login_id: str | None
    nickname: str | None


class Member(BaseModel):
    id: str
    login_id: str | None
    nickname: str | None
    email: str | None
    role: str
    status: str
    providers: list[str]
    created_at: datetime
    last_login_at: datetime | None
    logins: int
    courses_generated: int
    courses_saved: int
    last_ip: str | None
    last_seen_at: datetime | None


class MemberList(BaseModel):
    items: list[Member]
    total: int


class VisitRow(BaseModel):
    id: int
    at: datetime
    path: str
    device: str
    referrer: str | None
    ip: str | None
    visitor: str  # first 8 of the hash: the same browser across rows
    user: UserRef | None


class VisitList(BaseModel):
    items: list[VisitRow]
    next_before: int | None


class RequestedCourse(BaseModel):
    id: str
    label: str
    exists: bool  # a never-saved course is deleted after the TTL; the log keeps what was offered
    status: str | None
    total_price: int | None
    places: list[str]


class CourseRequestRow(BaseModel):
    id: int
    at: datetime
    ip: str | None
    user: UserRef | None
    where: str
    purpose: str
    party_size: int | None
    budget_total: int | None
    start_at: str | None
    taste: list[str]  # pace · wishes · style · move style, as sent
    latency_ms: int
    candidates: int
    warnings: list[str]
    courses: list[RequestedCourse]


class CourseRequestList(BaseModel):
    items: list[CourseRequestRow]
    next_before: int | None


def _ref(user: User | None) -> UserRef | None:
    return UserRef(id=user.public_id, login_id=user.login_id, nickname=user.nickname) if user else None


@router.get("/members", response_model=MemberList, summary="회원 목록 (최근 가입순, 검색)")
async def members(
    session: SessionDep,
    q: str | None = Query(default=None, max_length=100, description="아이디 · 닉네임 · 이메일"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> MemberList:
    stmt = select(User)
    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(User.login_id.ilike(like), User.nickname.ilike(like), User.email.ilike(like)))
    total = int(await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    users = (await session.scalars(stmt.order_by(User.created_at.desc()).offset(offset).limit(limit))).all()
    ids = [u.id for u in users]
    if not ids:
        return MemberList(items=[], total=total)

    def grouped(rows: Any) -> dict[int, Any]:
        return {uid: value for uid, value in rows.all()}

    providers: dict[int, list[str]] = {}
    for uid, provider in (
        await session.execute(
            select(OAuthAccount.user_id, OAuthAccount.provider).where(OAuthAccount.user_id.in_(ids))
        )
    ).all():
        providers.setdefault(uid, []).append(str(provider))
    logins = await session.execute(
        select(RefreshToken.user_id, func.count(), func.max(RefreshToken.created_at))
        .where(RefreshToken.user_id.in_(ids))
        .group_by(RefreshToken.user_id)
    )
    login_stats = {uid: (int(n), last) for uid, n, last in logins.all()}
    generated = grouped(
        await session.execute(
            select(RecommendationLog.user_id, func.count())
            .where(RecommendationLog.user_id.in_(ids))
            .group_by(RecommendationLog.user_id)
        )
    )
    saved = grouped(
        await session.execute(
            select(Course.user_id, func.count())
            .where(Course.user_id.in_(ids), Course.status.in_(SAVED))
            .group_by(Course.user_id)
        )
    )
    seen: dict[int, tuple[datetime, str | None]] = {}
    last_visit = (
        select(Visit.user_id, func.max(Visit.id).label("vid"))
        .where(Visit.user_id.in_(ids))
        .group_by(Visit.user_id)
        .subquery()
    )
    for uid, at, ip in (
        await session.execute(
            select(Visit.user_id, Visit.created_at, Visit.ip).join(last_visit, Visit.id == last_visit.c.vid)
        )
    ).all():
        seen[uid] = (at, ip)
    items = []
    for u in users:
        n_logins, last_login = login_stats.get(u.id, (0, None))
        at, ip = seen.get(u.id, (None, None))
        items.append(
            Member(
                id=u.public_id,
                login_id=u.login_id,
                nickname=u.nickname,
                email=u.email,
                role=u.role,
                status=u.status,
                providers=sorted(providers.get(u.id, [])) + (["아이디"] if u.login_id else []),
                created_at=u.created_at,
                last_login_at=last_login,
                logins=n_logins,
                courses_generated=int(generated.get(u.id, 0)),
                courses_saved=int(saved.get(u.id, 0)),
                last_ip=ip,
                last_seen_at=at,
            )
        )
    return MemberList(items=items, total=total)


@router.get("/visits", response_model=VisitList, summary="방문 로그 (최근순, IP 포함)")
async def visits(
    session: SessionDep,
    who: Who = "all",
    q: str | None = Query(default=None, max_length=100, description="IP · 경로 · 유입 일부"),
    limit: int = Query(default=100, ge=1, le=500),
    before: int | None = Query(default=None, description="이 id 보다 오래된 것 (다음 쪽)"),
) -> VisitList:
    stmt = select(Visit, User).outerjoin(User, User.id == Visit.user_id)
    if who == "member":
        stmt = stmt.where(Visit.user_id.is_not(None))
    elif who == "anonymous":
        stmt = stmt.where(Visit.user_id.is_(None))
    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Visit.ip.like(like), Visit.path.like(like), Visit.referrer.like(like)))
    if before is not None:
        stmt = stmt.where(Visit.id < before)
    rows = (await session.execute(stmt.order_by(Visit.id.desc()).limit(limit))).all()
    items = [
        VisitRow(
            id=v.id,
            at=v.created_at,
            path=v.path,
            device=v.device,
            referrer=v.referrer,
            ip=v.ip,
            visitor=v.visitor[:8],
            user=_ref(u),
        )
        for v, u in rows
    ]
    return VisitList(items=items, next_before=items[-1].id if len(items) == limit else None)


@router.get("/course-requests", response_model=CourseRequestList, summary="최근 코스 요청과 결과")
async def course_requests(
    session: SessionDep,
    who: Who = "all",
    limit: int = Query(default=30, ge=1, le=100),
    before: int | None = Query(default=None),
) -> CourseRequestList:
    stmt = select(RecommendationLog, User).outerjoin(User, User.id == RecommendationLog.user_id)
    if who == "member":
        stmt = stmt.where(RecommendationLog.user_id.is_not(None))
    elif who == "anonymous":
        stmt = stmt.where(RecommendationLog.user_id.is_(None))
    if before is not None:
        stmt = stmt.where(RecommendationLog.id < before)
    rows = (await session.execute(stmt.order_by(RecommendationLog.id.desc()).limit(limit))).all()
    if not rows:
        return CourseRequestList(items=[], next_before=None)

    regions = {i: n for i, n in (await session.execute(select(Region.id, Region.name))).all()}
    purposes = {c: n for c, n in (await session.execute(select(Purpose.code, Purpose.name))).all()}
    purpose_by_id = {i: n for i, n in (await session.execute(select(Purpose.id, Purpose.name))).all()}
    place_ids: set[str] = set()
    course_ids: set[str] = set()
    for log, _u in rows:
        for c in log.selected_courses or []:
            place_ids.update(str(p) for p in c.get("places") or [])
            if c.get("course_id"):
                course_ids.add(str(c["course_id"]))
        anchor = (log.request or {}).get("anchor") or {}
        if anchor.get("id"):
            place_ids.add(str(anchor["id"]))
    names = {
        pid: name
        for pid, name in (
            await session.execute(select(Place.public_id, Place.name).where(Place.public_id.in_(place_ids)))
        ).all()
    }
    courses = {
        cid: (status, price)
        for cid, status, price in (
            await session.execute(
                select(Course.public_id, Course.status, Course.total_price).where(
                    Course.public_id.in_(course_ids)
                )
            )
        ).all()
    }

    items = []
    for log, user in rows:
        req: dict[str, Any] = log.request or {}
        anchor = req.get("anchor") or {}
        where = (
            names.get(str(anchor.get("id")), "대학교")
            if anchor.get("id")
            else regions.get(log.region_id or -1)
            or " → ".join(str(r) for r in req.get("regions") or [])
            or str(req.get("region") or "-")
        )
        taste = [
            *([str(req["scene"])] if req.get("scene") else []),
            *(req.get("pace") or []),
            *(req.get("wishes") or []),
        ]
        if req.get("style") and req["style"] != "efficient":
            taste.append(str(req["style"]))
        if req.get("move_style"):
            taste.append(str(req["move_style"]))
        offered = []
        for c in log.selected_courses or []:
            status, price = courses.get(str(c.get("course_id")), (None, None))
            offered.append(
                RequestedCourse(
                    id=str(c.get("course_id") or ""),
                    label=str(c.get("label") or ""),
                    exists=status is not None,
                    status=status,
                    total_price=price,
                    places=[names.get(str(p), "(지워진 장소)") for p in c.get("places") or []],
                )
            )
        codes = Counter(str(w.get("code")) for w in log.warnings or [] if w.get("code"))
        items.append(
            CourseRequestRow(
                id=log.id,
                at=log.created_at,
                ip=log.ip,
                user=_ref(user),
                where=where,
                purpose=purposes.get(str(req.get("purpose")), purpose_by_id.get(log.purpose_id or -1, "-")),
                party_size=req.get("party_size"),
                budget_total=req.get("budget_total"),
                start_at=req.get("start_at"),
                taste=taste,
                latency_ms=log.latency_ms,
                candidates=log.candidate_count,
                warnings=sorted(codes),
                courses=offered,
            )
        )
    return CourseRequestList(items=items, next_before=items[-1].id if len(items) == limit else None)
