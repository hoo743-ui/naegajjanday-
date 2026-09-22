"""Edit keys for courses generated without an account (release audit P0, docs/28).

Before: an ownerless course was editable by anyone who had its link — a friend opening a shared link (or a
stranger) could swap the creator's places. Now `generate` issues a random key to the anonymous creator,
only its SHA-256 is stored on the course, and every edit must present the key in `X-Course-Key`.
Courses created before
this change (no hash) keep the old behaviour.

The header is read once per request by a router dependency and kept in a context variable, so the service's
ownership check reads it without threading a new argument through every method.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from contextvars import ContextVar
from typing import Annotated

from fastapi import Header

HEADER = "X-Course-Key"
_current: ContextVar[str | None] = ContextVar("course_key", default=None)


def new_key() -> str:
    return secrets.token_urlsafe(24)


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def matches(key: str | None, stored_hash: str | None) -> bool:
    return bool(key and stored_hash) and hmac.compare_digest(hash_key(key or ""), stored_hash or "")


def current_key() -> str | None:
    return _current.get()


def use_key(key: str | None) -> None:
    """For server-side callers (the chat tools) that act for the creator."""
    _current.set(key)


async def capture_course_key(
    x_course_key: Annotated[str | None, Header(alias=HEADER, max_length=64)] = None,
) -> None:
    _current.set(x_course_key)
