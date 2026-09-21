from __future__ import annotations

import base64
from typing import Any

from pydantic import BaseModel, Field


class LatLng(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class Problem(BaseModel):
    """RFC 9457 problem details (application/problem+json)."""

    type: str
    title: str
    status: int
    code: str
    detail: str | None = None
    meta: dict[str, Any] | None = None
    trace_id: str | None = None


class Ok(BaseModel):
    ok: bool = True


def encode_cursor(value: int | None) -> str | None:
    if value is None:
        return None
    return base64.urlsafe_b64encode(str(value).encode()).decode().rstrip("=")


def decode_cursor(cursor: str | None) -> int | None:
    if not cursor:
        return None
    try:
        return int(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode())
    except (ValueError, UnicodeDecodeError):
        return None
