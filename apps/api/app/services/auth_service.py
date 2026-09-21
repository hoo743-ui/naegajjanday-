"""OAuth2 (authorization code + PKCE + state), refresh-token rotation with family reuse detection,
logout with access-token `jti` denylist."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import errors, security
from app.core.cache import Cache
from app.core.config import Settings
from app.core.logging import get_logger
from app.infra.db.base import as_utc, utcnow
from app.infra.db.models import User
from app.repositories.user_repo import SqlUserRepository
from app.schemas import auth as dto
from app.services import retention_service as retention

logger = get_logger(__name__)

OAUTH_STATE_TTL_S = 600


@dataclass(frozen=True, slots=True)
class IssuedTokens:
    access: dto.TokenResponse
    refresh_token: str
    refresh_max_age: int


class AuthService:
    def __init__(
        self, settings: Settings, session: AsyncSession, cache: Cache, http: httpx.AsyncClient | None = None
    ) -> None:
        self._settings = settings
        self._s = session
        self._cache = cache
        self._http = http
        self._users = SqlUserRepository(session)

    # --- OAuth -------------------------------------------------------------------------------

    def _provider(self, provider: str) -> security.OAuthProviderConfig:
        cfg = security.OAUTH_PROVIDERS.get(provider)
        if cfg is None:
            raise errors.NotFound(f"'{provider}' 로그인은 지원하지 않아요.")
        client_id, client_secret = security.oauth_client(self._settings, provider)
        if not client_id or not client_secret:
            raise errors.OAuthNotConfigured(f"{provider.upper()}_CLIENT_ID / SECRET 이 설정되지 않았어요.")
        return cfg

    async def login_url(self, provider: str, redirect_to: str | None) -> str:
        self._provider(provider)
        state = security.new_state()
        verifier, challenge = security.new_pkce_pair()
        await self._cache.set(
            f"oauth:state:{state}",
            {"provider": provider, "verifier": verifier, "redirect_to": redirect_to},
            OAUTH_STATE_TTL_S,
        )
        return security.build_authorize_url(self._settings, provider, state=state, code_challenge=challenge)

    async def callback(self, provider: str, code: str, state: str) -> tuple[IssuedTokens, str | None]:
        cfg = self._provider(provider)
        saved = await self._cache.get(f"oauth:state:{state}")
        await self._cache.delete(f"oauth:state:{state}")  # one-time use
        if not saved or saved.get("provider") != provider:
            raise errors.BadRequest("로그인 요청이 만료됐어요. 다시 시도해 주세요.")
        client_id, client_secret = security.oauth_client(self._settings, provider)
        form = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": security.redirect_uri(self._settings, provider),
            "code_verifier": saved["verifier"],
            "state": state,
        }
        client = self._http or httpx.AsyncClient(timeout=10.0)
        try:
            token_resp = await client.post(cfg.token_url, data=form, headers={"Accept": "application/json"})
            token_resp.raise_for_status()
            provider_token = token_resp.json()["access_token"]
            info_resp = await client.get(
                cfg.userinfo_url, headers={"Authorization": f"Bearer {provider_token}"}
            )
            info_resp.raise_for_status()
            provider_user_id, email, nickname = security.parse_userinfo(provider, info_resp.json())
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            logger.warning("oauth.exchange_failed", provider=provider, error=str(exc))
            raise errors.Unauthorized("소셜 로그인에 실패했어요. 다시 시도해 주세요.") from exc
        finally:
            if self._http is None:
                await client.aclose()
        user = await self._users.upsert_oauth_user(provider, provider_user_id, email, nickname)
        if user.status == "suspended":
            raise errors.Forbidden("이용이 정지된 계정이에요.")
        if user.status == "deleting":
            if retention.is_purge_due(user, self._settings):
                # grace period over but the batch has not run yet: the promise is "gone for good",
                # so purge now and start a fresh account instead of resurrecting the old data
                await retention.purge_user(self._s, user)
                user = await self._users.upsert_oauth_user(provider, provider_user_id, email, nickname)
            else:  # logging in again within the grace period cancels the pending deletion
                user.status, user.delete_requested_at = "active", None
        tokens = await self.issue(user, family_id=str(uuid.uuid4()))
        await self._s.commit()
        return tokens, saved.get("redirect_to")

    # --- tokens ------------------------------------------------------------------------------

    async def issue(self, user: User, family_id: str) -> IssuedTokens:
        access, _claims = security.create_access_token(
            self._settings, user_public_id=user.public_id, role=user.role
        )
        refresh = security.new_refresh_token()
        ttl = timedelta(days=self._settings.refresh_token_ttl_days)
        await self._users.add_refresh_token(user.id, security.hash_token(refresh), family_id, utcnow() + ttl)
        return IssuedTokens(
            access=dto.TokenResponse(
                access_token=access, expires_in=self._settings.access_token_ttl_min * 60
            ),
            refresh_token=refresh,
            refresh_max_age=int(ttl.total_seconds()),
        )

    async def refresh(self, refresh_token: str | None) -> IssuedTokens:
        if not refresh_token:
            raise errors.Unauthorized("다시 로그인해 주세요.")
        row = await self._users.get_refresh_token(security.hash_token(refresh_token))
        if row is None:
            raise errors.Unauthorized("다시 로그인해 주세요.")
        if row.revoked_at is not None:
            # a rotated token came back: someone else holds a copy → kill the whole family
            await self._users.revoke_family(row.family_id)
            await self._s.commit()
            logger.warning("auth.refresh_reuse_detected", user_id=row.user_id, family_id=row.family_id)
            raise errors.TokenReuseDetected()
        expires_at = as_utc(row.expires_at)
        if expires_at is None or expires_at <= datetime.now(UTC):
            raise errors.Unauthorized("로그인이 만료됐어요. 다시 로그인해 주세요.")
        user = await self._users.get(row.user_id)
        if user is None or user.status != "active":
            raise errors.Unauthorized()
        row.revoked_at = utcnow()
        tokens = await self.issue(user, family_id=row.family_id)
        await self._s.commit()
        return tokens

    async def logout(self, refresh_token: str | None, claims: security.AccessClaims | None) -> None:
        if refresh_token:
            row = await self._users.get_refresh_token(security.hash_token(refresh_token))
            if row is not None:
                await self._users.revoke_family(row.family_id)
        if claims is not None:
            ttl = max(1, int((claims.exp - datetime.now(UTC)).total_seconds()))
            await self._cache.set(f"jwt:deny:{claims.jti}", 1, ttl)
        await self._s.commit()

    # --- profile -----------------------------------------------------------------------------

    @staticmethod
    def user_out(user: User) -> dto.UserOut:
        created = as_utc(user.created_at) or utcnow()
        return dto.UserOut(
            id=user.public_id, email=user.email, nickname=user.nickname, role=user.role,
            status=user.status, created_at=created,
        )  # fmt: skip

    async def patch_me(self, user: User, body: dto.UserPatch) -> dto.UserOut:
        if body.nickname is not None:
            user.nickname = body.nickname
        await self._s.commit()
        return self.user_out(user)

    async def get_preferences(self, user: User) -> dto.PreferencesBody:
        pref = await self._users.get_preference(user.id)
        if pref is None:
            return dto.PreferencesBody()
        return dto.PreferencesBody(
            liked_tags=list(pref.liked_tags or []),
            disliked_tags=list(pref.disliked_tags or []),
            category_weights=dict(pref.category_weights or {}),
            default_transport=pref.default_transport,
        )

    async def put_preferences(self, user: User, body: dto.PreferencesBody) -> dto.PreferencesBody:
        pref = await self._users.ensure_preference(user.id)
        pref.liked_tags, pref.disliked_tags = body.liked_tags, body.disliked_tags
        pref.category_weights = {k: max(-1.0, min(1.0, v)) for k, v in body.category_weights.items()}
        pref.default_transport = body.default_transport
        await self._s.commit()
        return await self.get_preferences(user)

    async def request_deletion(self, user: User) -> dto.DeleteAccountResponse:
        """개인정보보호법: soft-delete now (every token dies, `status != active` blocks the API), then
        `retention_service.purge_deleted_accounts` hard-deletes after `account_purge_grace_days`."""
        user.status, user.delete_requested_at = "deleting", utcnow()
        from sqlalchemy import update

        from app.infra.db.models import RefreshToken

        await self._s.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=utcnow())
        )
        await self._s.commit()
        return dto.DeleteAccountResponse(
            status="deleting",
            purge_after=utcnow() + timedelta(days=self._settings.account_purge_grace_days),
        )
