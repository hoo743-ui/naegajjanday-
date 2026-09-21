"""JWT access tokens, opaque rotating refresh tokens, OAuth2 authorization-code + PKCE helpers."""

from __future__ import annotations

import base64
import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import jwt

from app.core.config import Settings


@dataclass(frozen=True, slots=True)
class AccessClaims:
    sub: str  # user public_id
    role: str
    jti: str
    exp: datetime


class TokenError(Exception):
    pass


def create_access_token(settings: Settings, *, user_public_id: str, role: str) -> tuple[str, AccessClaims]:
    now = datetime.now(UTC)
    claims = AccessClaims(
        sub=user_public_id,
        role=role,
        jti=uuid.uuid4().hex,
        exp=now + timedelta(minutes=settings.access_token_ttl_min),
    )
    payload = {
        "iss": settings.jwt_issuer,
        "sub": claims.sub,
        "role": claims.role,
        "jti": claims.jti,
        "iat": int(now.timestamp()),
        "exp": int(claims.exp.timestamp()),
        "typ": "access",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm), claims


def decode_access_token(settings: Settings, token: str) -> AccessClaims:
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "sub", "jti"]},
        )
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc
    if payload.get("typ") != "access":
        raise TokenError("wrong token type")
    return AccessClaims(
        sub=str(payload["sub"]),
        role=str(payload.get("role", "user")),
        jti=str(payload["jti"]),
        exp=datetime.fromtimestamp(int(payload["exp"]), tz=UTC),
    )


# --- refresh tokens: opaque, only the SHA-256 hash is stored ---------------------------------


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# --- OAuth2 authorization code + PKCE --------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OAuthProviderConfig:
    name: str
    authorize_url: str
    token_url: str
    userinfo_url: str
    scope: str


OAUTH_PROVIDERS: dict[str, OAuthProviderConfig] = {
    "kakao": OAuthProviderConfig(
        "kakao",
        "https://kauth.kakao.com/oauth/authorize",
        "https://kauth.kakao.com/oauth/token",
        "https://kapi.kakao.com/v2/user/me",
        "profile_nickname account_email",
    ),
    "naver": OAuthProviderConfig(
        "naver",
        "https://nid.naver.com/oauth2.0/authorize",
        "https://nid.naver.com/oauth2.0/token",
        "https://openapi.naver.com/v1/nid/me",
        "",
    ),
    "google": OAuthProviderConfig(
        "google",
        "https://accounts.google.com/o/oauth2/v2/auth",
        "https://oauth2.googleapis.com/token",
        "https://openidconnect.googleapis.com/v1/userinfo",
        "openid email profile",
    ),
}


def new_state() -> str:
    return secrets.token_urlsafe(24)


def new_pkce_pair() -> tuple[str, str]:
    """Returns (code_verifier, S256 code_challenge)."""
    verifier = secrets.token_urlsafe(64)[:96]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def oauth_client(settings: Settings, provider: str) -> tuple[str | None, str | None]:
    return (
        getattr(settings, f"{provider}_client_id", None),
        getattr(settings, f"{provider}_client_secret", None),
    )


def redirect_uri(settings: Settings, provider: str) -> str:
    return f"{settings.public_base_url.rstrip('/')}/v1/auth/{provider}/callback"


def build_authorize_url(settings: Settings, provider: str, *, state: str, code_challenge: str) -> str:
    cfg = OAUTH_PROVIDERS[provider]
    client_id, _ = oauth_client(settings, provider)
    params = {
        "response_type": "code",
        "client_id": client_id or "",
        "redirect_uri": redirect_uri(settings, provider),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    if cfg.scope:
        params["scope"] = cfg.scope
    return f"{cfg.authorize_url}?{urlencode(params)}"


def parse_userinfo(provider: str, data: dict[str, Any]) -> tuple[str, str | None, str | None]:
    """(provider_user_id, email, nickname) from each provider's userinfo payload."""
    if provider == "kakao":
        account = data.get("kakao_account") or {}
        email = account.get("email") if account.get("is_email_verified", True) else None
        return str(data["id"]), email, (account.get("profile") or {}).get("nickname")
    if provider == "naver":
        resp = data.get("response") or {}
        return str(resp["id"]), resp.get("email"), resp.get("nickname") or resp.get("name")
    email = data.get("email") if data.get("email_verified", True) else None
    return str(data["sub"]), email, data.get("name")
