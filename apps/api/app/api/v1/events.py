"""`POST /events` — the web's `track()` events, first-party (docs/62). Fire and forget: batched by the
browser, sent with `fetch(keepalive)` or `navigator.sendBeacon` (a `text/plain` body, so no CORS preflight).

Only event names from `services/event_catalog.py` are stored, each with its whitelisted properties. The
browser's random id is kept as the same keyed hash `visit.visitor` uses; IPs are only counted for the rate
limit, never stored. `DNT: 1` / `Sec-GPC: 1` → nothing is stored.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select

from app.api.v1.visits import NOT_A_PERSON
from app.core import errors, security
from app.core.deps import ContainerDep, CredentialsDep, SessionDep, client_ip
from app.infra.db.base import utcnow
from app.infra.db.models import AppEvent, User
from app.services import event_catalog

router = APIRouter(tags=["events"])

MAX_BODY_BYTES = 32 * 1024
MAX_EVENTS = 50
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
MAX_AGE = timedelta(days=1)  # a batch kept offline longer than this is dated when it arrives


class EventIn(BaseModel):
    name: str = Field(max_length=64)
    props: dict[str, Any] = Field(default_factory=dict)
    course_id: str | None = Field(default=None, max_length=64)
    ts: float | None = Field(default=None, description="ms since epoch, the browser's clock")
    path: str | None = Field(default=None, max_length=500)


class EventBatch(BaseModel):
    device_id: str = Field(min_length=8, max_length=64, description="브라우저가 만든 임의 id (localStorage)")
    events: list[EventIn] = Field(min_length=1, max_length=MAX_EVENTS)


def device_hash(secret: str, device_id: str) -> str:
    """The same keyed hash as `visit.visitor`, so a device's events and page views line up."""
    return hmac.new(secret.encode(), device_id.encode(), hashlib.sha256).hexdigest()[:32]


def _when(ts: float | None, now: datetime) -> datetime:
    if ts is None:
        return now
    try:
        at = datetime.fromtimestamp(ts / 1000, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return now
    return at if now - MAX_AGE <= at <= now else now


def _path(raw: str | None) -> str | None:
    if not raw or not raw.startswith("/"):
        return None
    return raw.split("?")[0].split("#")[0][:200]


async def _limit(container: ContainerDep, scope: str, spec: str, identity: str) -> None:
    limit, window = container.settings.parse_limit(spec)
    result = await container.rate_limiter.hit(scope, identity, limit, window)
    if not result.allowed:
        raise errors.RateLimited(
            meta={"limit": limit, "window_s": window},
            headers={**result.headers, "Retry-After": str(result.reset_s)},
        )


@router.post(
    "/events",
    status_code=202,
    summary="제품 이벤트 기록 (1자 분석, docs/62) — 목록에 있는 이름 · 속성만",
    responses={204: {"description": "Do-Not-Track · 봇 · 관리자 화면: 저장하지 않음"}},
)
async def record_events(
    request: Request,
    session: SessionDep,
    container: ContainerDep,
    credentials: CredentialsDep,
) -> Response:
    settings = container.settings
    ua = request.headers.get("user-agent", "")
    if request.headers.get("dnt") == "1" or request.headers.get("sec-gpc") == "1":
        return Response(status_code=204)
    if not ua or NOT_A_PERSON.search(ua):
        return Response(status_code=204)
    if settings.rate_limit_enabled:
        await _limit(container, "events_ip", settings.rl_events_ip, client_ip(request))
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise errors.PayloadTooLarge(f"이벤트 묶음은 {MAX_BODY_BYTES // 1024}KB 까지예요.")
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        raise errors.PayloadTooLarge(f"이벤트 묶음은 {MAX_BODY_BYTES // 1024}KB 까지예요.")
    try:  # sendBeacon posts text/plain: read the body as JSON whatever the content type says
        batch = EventBatch.model_validate_json(raw)
    except ValidationError as exc:
        raise errors.ValidationFailed(
            "이벤트 형식이 맞지 않아요.", meta={"errors": exc.error_count()}
        ) from exc

    if settings.rate_limit_enabled:
        await _limit(container, "events_device", settings.rl_events_device, batch.device_id)

    user_id: int | None = None
    if credentials is not None:  # sendBeacon cannot carry the token: those events stay anonymous
        try:
            claims = security.decode_access_token(settings, credentials.credentials)
            user_id = await session.scalar(select(User.id).where(User.public_id == claims.sub))
        except security.TokenError:
            user_id = None

    device = device_hash(settings.jwt_secret, batch.device_id)
    now = utcnow()
    accepted, unknown = 0, []
    for e in batch.events:
        if not event_catalog.is_known(e.name):
            unknown.append(e.name[:48])
            continue
        path = _path(e.path)
        if path is not None and path.startswith("/admin"):
            continue
        props = dict(e.props)
        course = e.course_id or props.get("course_id")
        session.add(
            AppEvent(
                name=e.name,
                device=device,
                user_id=user_id,
                course_id=course.lower()
                if isinstance(course, str) and UUID_RE.match(course.lower())
                else None,
                path=path,
                props=event_catalog.clean_props(e.name, props),
                created_at=_when(e.ts, now),
            )
        )
        accepted += 1
    if accepted == 0 and unknown:
        raise errors.ValidationFailed("목록에 없는 이벤트예요.", meta={"unknown": sorted(set(unknown))[:10]})
    await session.commit()
    body: dict[str, Any] = {"accepted": accepted, "dropped": len(batch.events) - accepted}
    if unknown:
        body["unknown"] = sorted(set(unknown))[:10]
    return JSONResponse(body, status_code=202)
