"""FastAPI dependencies: container, DB session, auth, RBAC, rate limiting, service factories."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import errors, security
from app.core.cache import Cache
from app.core.config import Settings
from app.core.rate_limit import RateLimiter
from app.domain.routing.travel_time import TravelTimeProvider
from app.infra.analytics.base import EventTracker
from app.infra.db.models import User
from app.infra.db.session import Database
from app.infra.llm.base import LLMProvider
from app.infra.search.client import PlaceSearch
from app.prompts.loader import PromptLoader
from app.repositories.user_repo import SqlUserRepository

ADMIN_ROLES = frozenset({"admin", "operator"})
bearer = HTTPBearer(auto_error=False, description="JWT access token (15분)")


@dataclass(slots=True)
class Container:
    """Process-wide singletons, built once in the app lifespan."""

    settings: Settings
    db: Database
    cache: Cache
    rate_limiter: RateLimiter
    llm: LLMProvider
    tracker: EventTracker
    prompts: PromptLoader
    search: PlaceSearch | None
    travel: TravelTimeProvider | None


def get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


ContainerDep = Annotated[Container, Depends(get_container)]


async def get_session(container: ContainerDep) -> AsyncIterator[AsyncSession]:
    """One session per request. Services commit explicitly; anything left over is rolled back."""
    async with container.db.sessionmaker() as session:
        try:
            yield session
        finally:
            await session.rollback()


SessionDep = Annotated[AsyncSession, Depends(get_session)]
CredentialsDep = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]


async def get_claims(container: ContainerDep, credentials: CredentialsDep) -> security.AccessClaims | None:
    if credentials is None:
        return None
    try:
        claims = security.decode_access_token(container.settings, credentials.credentials)
    except security.TokenError as exc:
        raise errors.Unauthorized("로그인이 만료됐어요. 다시 로그인해 주세요.") from exc
    if await container.cache.get(f"jwt:deny:{claims.jti}") is not None:
        raise errors.Unauthorized("로그아웃된 토큰이에요.")
    return claims


ClaimsDep = Annotated[security.AccessClaims | None, Depends(get_claims)]


async def get_optional_user(request: Request, session: SessionDep, claims: ClaimsDep) -> User | None:
    if claims is None:
        return None
    user = await SqlUserRepository(session).get_by_public_id(claims.sub)
    if user is None or user.status != "active":
        raise errors.Unauthorized()
    request.state.user_public_id = user.public_id
    return user


OptionalUser = Annotated[User | None, Depends(get_optional_user)]


async def get_current_user(user: OptionalUser) -> User:
    if user is None:
        raise errors.Unauthorized()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_admin(user: CurrentUser) -> User:
    if user.role not in ADMIN_ROLES:  # the DB role is authoritative, not the token claim
        raise errors.Forbidden("관리자만 사용할 수 있어요.")
    return user


AdminUser = Annotated[User, Depends(require_admin)]


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _limit_spec(settings: Settings, scope: str, signed_in: bool) -> tuple[str, str]:
    """(limit spec, counter name) for a scope."""
    if scope == "generate":
        if signed_in:
            return settings.rl_generate_user, "generate_user"
        return settings.rl_generate_anon, "generate_anon"
    if scope == "chat":
        return settings.rl_chat, "chat"
    if scope == "auth":
        return settings.rl_auth, "auth"
    return settings.rl_read, "read"


async def _hit(response: Response, container: Container, scope: str, identity: str, signed_in: bool) -> None:
    settings = container.settings
    spec, name = _limit_spec(settings, scope, signed_in)
    limit, window = settings.parse_limit(spec)
    result = await container.rate_limiter.hit(name, identity, limit, window)
    response.headers.update(result.headers)
    if not result.allowed:
        raise errors.RateLimited(
            meta={"limit": limit, "window_s": window},
            headers={**result.headers, "Retry-After": str(result.reset_s)},
        )


def rate_limit(scope: str) -> Callable[..., Awaitable[None]]:
    """Sliding-window limits of doc 03 §1. `generate` differs for anonymous IPs and signed-in users."""

    async def dependency(
        request: Request, response: Response, container: ContainerDep, claims: ClaimsDep
    ) -> None:
        if not container.settings.rate_limit_enabled:
            return
        identity = f"u:{claims.sub}" if claims else f"ip:{client_ip(request)}"
        await _hit(response, container, scope, identity, signed_in=claims is not None)

    return dependency


def ip_rate_limit(scope: str) -> Callable[..., Awaitable[None]]:
    """Same limits, always counted per client IP and without reading the bearer token — for sign-up /
    login, where a stale access token must not answer 401 and a token must not buy a separate budget."""

    async def dependency(request: Request, response: Response, container: ContainerDep) -> None:
        if not container.settings.rate_limit_enabled:
            return
        await _hit(response, container, scope, f"ip:{client_ip(request)}", signed_in=False)

    return dependency
