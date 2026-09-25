"""`POST /visits` — a first-party page view (docs/50). Fire and forget: it never fails the page."""

from __future__ import annotations

import hashlib
import hmac
import re
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core import security
from app.core.deps import ContainerDep, CredentialsDep, SessionDep, client_ip, rate_limit
from app.infra.db.models import User, Visit

router = APIRouter(tags=["visits"], dependencies=[Depends(rate_limit("read"))])

# crawlers, link previews (카카오톡 · 슬랙 미리보기) and our own headless checks are not visitors
NOT_A_PERSON = re.compile(
    r"bot|crawl|spider|slurp|preview|scrap|headless|lighthouse|facebookexternalhit", re.I
)


class VisitIn(BaseModel):
    visitor_id: str = Field(min_length=8, max_length=64, description="브라우저가 만든 임의 id (localStorage)")
    path: str = Field(max_length=200)
    referrer: str | None = Field(
        default=None, max_length=500, description="document.referrer — 호스트만 남긴다"
    )


def device_of(user_agent: str) -> str:
    ua = user_agent.lower()
    if "ipad" in ua or "tablet" in ua:
        return "tablet"
    return "mobile" if "mobi" in ua or "android" in ua or "iphone" in ua else "desktop"


def referrer_host(referrer: str | None, own_host: str | None) -> str | None:
    host = (urlparse(referrer).hostname or "").removeprefix("www.") if referrer else ""
    if not host or (own_host and host == own_host.removeprefix("www.")):
        return None  # typed in, a bookmark, or a click inside the site
    return host[:120]


@router.post("/visits", status_code=204, summary="페이지 방문 기록 (1자 분석, 로그인 · 비로그인 모두)")
async def record_visit(
    body: VisitIn,
    request: Request,
    session: SessionDep,
    container: ContainerDep,
    credentials: CredentialsDep,
) -> Response:
    ua = request.headers.get("user-agent", "")
    if not ua or NOT_A_PERSON.search(ua) or not body.path.startswith("/") or body.path.startswith("/admin"):
        return Response(status_code=204)
    user_id: int | None = None
    if credentials is not None:  # an expired token is still a visit, just not a logged-in one
        try:
            claims = security.decode_access_token(container.settings, credentials.credentials)
            user_id = await session.scalar(select(User.id).where(User.public_id == claims.sub))
        except security.TokenError:
            user_id = None
    key = container.settings.jwt_secret.encode()
    visitor = hmac.new(key, body.visitor_id.encode(), hashlib.sha256).hexdigest()[:32]
    own = urlparse(str(container.settings.web_base_url or "")).hostname
    session.add(
        Visit(
            visitor=visitor,
            user_id=user_id,
            path=body.path.split("?")[0][:200],
            referrer=referrer_host(body.referrer, own),
            device=device_of(ua),
            ip=client_ip(request)[:45],
        )
    )
    await session.commit()
    return Response(status_code=204)
