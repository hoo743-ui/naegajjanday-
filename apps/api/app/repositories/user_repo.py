from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.db.base import utcnow
from app.infra.db.models import OAuthAccount, RefreshToken, User, UserPreference


class SqlUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self, user_id: int) -> User | None:
        return await self._s.get(User, user_id)

    async def get_by_public_id(self, public_id: str) -> User | None:
        return await self._s.scalar(select(User).where(User.public_id == public_id))

    async def get_by_email(self, email: str) -> User | None:
        return await self._s.scalar(select(User).where(User.email == email))

    async def get_preference(self, user_id: int) -> UserPreference | None:
        return await self._s.get(UserPreference, user_id)

    async def ensure_preference(self, user_id: int) -> UserPreference:
        pref = await self.get_preference(user_id)
        if pref is None:
            pref = UserPreference(user_id=user_id, liked_tags=[], disliked_tags=[], category_weights={})
            self._s.add(pref)
            await self._s.flush()
        return pref

    async def create(self, *, email: str | None, nickname: str | None, role: str = "user") -> User:
        user = User(email=email, nickname=nickname, role=role)
        self._s.add(user)
        await self._s.flush()
        return user

    async def upsert_oauth_user(
        self, provider: str, provider_user_id: str, email: str | None, nickname: str | None
    ) -> User:
        account = await self._s.scalar(
            select(OAuthAccount).where(
                OAuthAccount.provider == provider, OAuthAccount.provider_user_id == provider_user_id
            )
        )
        if account is not None:
            user = await self._s.get(User, account.user_id)
            if user is not None:
                return user
        user = (await self.get_by_email(email)) if email else None  # a verified e-mail links accounts
        if user is None:
            user = await self.create(email=email, nickname=nickname)
        self._s.add(OAuthAccount(user_id=user.id, provider=provider, provider_user_id=provider_user_id))
        await self._s.flush()
        return user

    async def due_for_purge(self, cutoff: datetime, limit: int | None = None) -> list[User]:
        """Accounts whose deletion was requested before `cutoff` and never cancelled by a new login."""
        stmt = select(User).where(
            User.status == "deleting",
            User.delete_requested_at.is_not(None),
            User.delete_requested_at <= cutoff,
        )
        stmt = stmt.order_by(User.id)
        return list((await self._s.scalars(stmt.limit(limit) if limit else stmt)).all())

    # --- refresh tokens ----------------------------------------------------------------------

    async def add_refresh_token(
        self, user_id: int, token_hash: str, family_id: str, expires_at: datetime
    ) -> None:
        self._s.add(
            RefreshToken(user_id=user_id, token_hash=token_hash, family_id=family_id, expires_at=expires_at)
        )
        await self._s.flush()

    async def get_refresh_token(self, token_hash: str) -> RefreshToken | None:
        return await self._s.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))

    async def revoke_family(self, family_id: str) -> None:
        await self._s.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=utcnow())
        )
