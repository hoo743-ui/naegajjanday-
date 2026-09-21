"""Audit trail for admin writes. Rows join the caller's transaction, so a failed write leaves no log."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AdminUser, SessionDep, client_ip
from app.infra.db.models import AuditLog, User


class AuditLogger:
    def __init__(self, session: AsyncSession, actor: User, ip: str | None, user_agent: str | None) -> None:
        self._s = session
        self.actor = actor
        self._ip = ip
        self._ua = user_agent

    def record(
        self, action: str, entity: str, entity_id: str | int | None, diff: dict[str, Any] | None = None
    ) -> None:
        self._s.add(
            AuditLog(
                actor_id=self.actor.id,
                action=action,
                entity=entity,
                entity_id=str(entity_id) if entity_id is not None else None,
                diff=diff or {},
                ip=self._ip,
                user_agent=(self._ua or "")[:300] or None,
            )
        )


def get_audit(request: Request, session: SessionDep, admin: AdminUser) -> AuditLogger:
    return AuditLogger(session, admin, client_ip(request), request.headers.get("user-agent"))


AuditDep = Annotated[AuditLogger, Depends(get_audit)]
