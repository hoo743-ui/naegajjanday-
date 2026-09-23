from __future__ import annotations

from typing import Annotated, Literal, get_args
from urllib.parse import urlencode

from fastapi import APIRouter, Cookie, Depends, Query, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from app.api.v1.responses import PROBLEMS
from app.core import errors, security
from app.core.deps import ContainerDep, CredentialsDep, client_ip, ip_rate_limit, rate_limit
from app.schemas.auth import AuthProviderOut, AuthProvidersResponse, LoginBody, SignupBody, TokenResponse
from app.schemas.common import Ok
from app.services.auth_service import IssuedTokens
from app.services.factory import AuthServiceDep

# The rate limit is declared per route (not on the router): its dependency validates the bearer token and
# would answer 401 for an expired one, which `/logout` must survive.
router = APIRouter(prefix="/auth", tags=["auth"])
READ_LIMIT = [Depends(rate_limit("read"))]
# sign-up / login: a much tighter per-IP budget (password guessing), independent of any bearer token
AUTH_LIMIT = [Depends(ip_rate_limit("auth"))]

Provider = Literal["kakao", "naver", "google"]

# same key AuthService.login_url() writes; peeked here only to learn where to send a failed login back to
_OAUTH_STATE_KEY = "oauth:state:{state}"


def _set_refresh_cookie(response: Response, container: ContainerDep, tokens: IssuedTokens) -> None:
    s = container.settings
    response.set_cookie(
        s.refresh_cookie_name,
        tokens.refresh_token,
        max_age=tokens.refresh_max_age,
        httponly=True,
        secure=s.cookie_secure,
        samesite="lax",
        path="/v1/auth",
    )


def _safe_redirect(container: ContainerDep, target: str | None) -> str | None:
    """Open-redirect guard: only relative paths on the web app are accepted."""
    if target and target.startswith("/") and not target.startswith("//"):
        return f"{container.settings.web_base_url.rstrip('/')}{target}"
    return None


def _login_error_redirect(container: ContainerDep, code: str, next_path: str | None) -> RedirectResponse:
    """The OAuth flow is a top-level navigation: a failure returns to the web login page, not to raw JSON."""
    query = {"error": code}
    if next_path:
        query["next"] = next_path
    base = container.settings.web_base_url.rstrip("/")
    return RedirectResponse(f"{base}/login?{urlencode(query)}", status_code=303)


def _error_code(exc: errors.AppError) -> str:
    if isinstance(exc, errors.OAuthNotConfigured):
        return "oauth_not_configured"
    if isinstance(exc, errors.Forbidden):
        return "account_suspended"
    return "oauth_failed"


async def _lenient_claims(
    container: ContainerDep, credentials: CredentialsDep
) -> security.AccessClaims | None:
    """Logout must work with an expired / missing access token, so a bad token is simply ignored."""
    if credentials is None:
        return None
    try:
        return security.decode_access_token(container.settings, credentials.credentials)
    except security.TokenError:
        return None


async def _logout_rate_limit(request: Request, container: ContainerDep) -> None:
    settings = container.settings
    if not settings.rate_limit_enabled:
        return
    limit, window = settings.parse_limit(settings.rl_read)
    result = await container.rate_limiter.hit("read", f"ip:{client_ip(request)}", limit, window)
    if not result.allowed:
        raise errors.RateLimited(
            meta={"limit": limit, "window_s": window},
            headers={**result.headers, "Retry-After": str(result.reset_s)},
        )


@router.get(
    "/providers",
    response_model=AuthProvidersResponse,
    dependencies=READ_LIMIT,
    summary="소셜 로그인 제공자별 사용 가능 여부 (client id + secret 이 모두 설정됐는가)",
)
async def providers(container: ContainerDep) -> AuthProvidersResponse:
    items = []
    for name in get_args(Provider):
        client_id, client_secret = security.oauth_client(container.settings, name)
        items.append(AuthProviderOut(provider=name, enabled=bool(client_id and client_secret)))
    return AuthProvidersResponse(items=items)


@router.post(
    "/signup",
    response_model=TokenResponse,
    status_code=201,
    responses=PROBLEMS(409, 422, 429),
    dependencies=AUTH_LIMIT,
    summary="아이디·비밀번호 가입 (이메일 인증 없음, 바로 활성) → access 발급 + refresh 쿠키",
)
async def signup(
    body: SignupBody, response: Response, service: AuthServiceDep, container: ContainerDep
) -> TokenResponse:
    tokens = await service.signup(body)
    _set_refresh_cookie(response, container, tokens)
    return tokens.access


@router.post(
    "/login",
    response_model=TokenResponse,
    responses=PROBLEMS(401, 403, 422, 429),
    dependencies=AUTH_LIMIT,
    summary="아이디·비밀번호 로그인 → access 발급 + refresh 쿠키",
)
async def password_login(
    body: LoginBody, response: Response, service: AuthServiceDep, container: ContainerDep
) -> TokenResponse:
    tokens = await service.login_password(body)
    _set_refresh_cookie(response, container, tokens)
    return tokens.access


@router.get(
    "/{provider}/login",
    status_code=307,
    responses={
        307: {"description": "Provider 인증 화면으로 이동"},
        303: {"description": "실패 + redirect_to 가 있으면 웹 로그인 화면으로 (?error=코드)"},
        **PROBLEMS(503),
    },
    dependencies=READ_LIMIT,
    summary="OAuth2 Authorization Code + PKCE 시작",
)
async def login(
    provider: Provider,
    service: AuthServiceDep,
    container: ContainerDep,
    redirect_to: Annotated[str | None, Query(max_length=200)] = None,
) -> RedirectResponse:
    try:
        url = await service.login_url(provider, redirect_to)
    except errors.AppError as exc:
        if _safe_redirect(container, redirect_to) is None:
            raise
        return _login_error_redirect(container, _error_code(exc), redirect_to)
    return RedirectResponse(url, status_code=307)


@router.get(
    "/{provider}/callback",
    response_model=TokenResponse,
    responses={
        303: {"description": "웹으로 복귀. 실패하면 웹 로그인 화면으로 (?error=코드)"},
        **PROBLEMS(400, 401, 503),
    },
    dependencies=READ_LIMIT,
    summary="토큰 교환 → 사용자 upsert → access 발급 + refresh 쿠키",
)
async def callback(
    provider: Provider,
    service: AuthServiceDep,
    container: ContainerDep,
    code: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    error: Annotated[str | None, Query()] = None,
) -> Response:
    # where the login started from; without it (API clients, expired state) errors stay problem+json
    saved = await container.cache.get(_OAUTH_STATE_KEY.format(state=state)) if state else None
    origin = saved.get("redirect_to") if isinstance(saved, dict) else None
    origin = origin if _safe_redirect(container, origin) else None

    if error or not code or not state:
        if state:
            await container.cache.delete(_OAUTH_STATE_KEY.format(state=state))  # one-time use
        if origin:
            return _login_error_redirect(container, "oauth_cancelled", origin)
        raise errors.BadRequest("소셜 로그인이 취소됐어요.")
    try:
        tokens, redirect_to = await service.callback(provider, code, state)
    except errors.AppError as exc:
        if origin is None:
            raise
        return _login_error_redirect(container, _error_code(exc), origin)
    target = _safe_redirect(container, redirect_to)
    response: Response
    if target:
        # the SPA calls POST /auth/refresh on load to obtain its access token from the cookie
        response = RedirectResponse(target, status_code=303)
    else:
        response = JSONResponse(tokens.access.model_dump())
    _set_refresh_cookie(response, container, tokens)
    return response


@router.post(
    "/refresh",
    response_model=TokenResponse,
    responses=PROBLEMS(401),
    dependencies=READ_LIMIT,
    summary="Refresh rotation",
)
async def refresh(
    response: Response,
    service: AuthServiceDep,
    container: ContainerDep,
    rt: Annotated[str | None, Cookie()] = None,
) -> TokenResponse:
    tokens = await service.refresh(rt)
    _set_refresh_cookie(response, container, tokens)
    return tokens.access


@router.post(
    "/logout",
    response_model=Ok,
    dependencies=[Depends(_logout_rate_limit)],
    summary="refresh 폐기 + access jti denylist (멱등: access token 이 만료됐거나 없어도 200)",
)
async def logout(
    response: Response,
    service: AuthServiceDep,
    container: ContainerDep,
    claims: Annotated[security.AccessClaims | None, Depends(_lenient_claims)],
    rt: Annotated[str | None, Cookie()] = None,
) -> Ok:
    await service.logout(rt, claims)
    response.delete_cookie(container.settings.refresh_cookie_name, path="/v1/auth")
    return Ok()
