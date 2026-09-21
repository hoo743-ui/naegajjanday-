from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["Bearer"] = "Bearer"
    expires_in: int


class AuthProviderOut(BaseModel):
    provider: Literal["kakao", "naver", "google"]
    enabled: bool  # client id AND secret are configured


class AuthProvidersResponse(BaseModel):
    items: list[AuthProviderOut]


class UserOut(BaseModel):
    id: str
    email: str | None = None
    nickname: str | None = None
    provider: str | None = None  # first linked OAuth account (kakao | naver | google); None for seeded users
    role: str
    status: str
    created_at: datetime


class UserPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nickname: str | None = Field(default=None, min_length=1, max_length=30)


class PreferencesBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    liked_tags: list[str] = Field(default_factory=list, max_length=30)
    disliked_tags: list[str] = Field(default_factory=list, max_length=30)
    category_weights: dict[str, float] = Field(default_factory=dict)
    default_transport: Literal["walk", "transit", "car"] = "walk"


class DeleteAccountResponse(BaseModel):
    status: str
    purge_after: datetime
