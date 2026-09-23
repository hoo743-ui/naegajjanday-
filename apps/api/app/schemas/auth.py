from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_core import PydanticCustomError

LOGIN_ID_MIN, LOGIN_ID_MAX = 4, 20
PASSWORD_MIN, PASSWORD_MAX = 8, 72
NICKNAME_MAX = 30
_LOGIN_ID_RE = re.compile(r"^[a-z0-9._-]+$")
_HAS_LETTER = re.compile(r"[A-Za-z]")
_HAS_DIGIT = re.compile(r"[0-9]")
# login input is never validated against the sign-up rules (that would leak them); only absurd sizes stop
_LOGIN_INPUT_MAX = 256


def normalize_login_id(value: str) -> str:
    """Login ids are case-insensitive: trimmed and stored lowercase."""
    return value.strip().lower()


def _invalid(field: str, message: str) -> PydanticCustomError:
    # PydanticCustomError keeps `msg` exactly as written, so the 422 problem shows the Korean text
    return PydanticCustomError(f"{field}_invalid", message)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["Bearer"] = "Bearer"
    expires_in: int


class AuthProviderOut(BaseModel):
    provider: Literal["kakao", "naver", "google"]
    enabled: bool  # client id AND secret are configured


class AuthProvidersResponse(BaseModel):
    items: list[AuthProviderOut]


class SignupBody(BaseModel):
    login_id: str
    password: str
    nickname: str | None = None

    @field_validator("login_id")
    @classmethod
    def _login_id(cls, value: str) -> str:
        value = normalize_login_id(value)
        if not LOGIN_ID_MIN <= len(value) <= LOGIN_ID_MAX:
            raise _invalid("login_id", f"아이디는 {LOGIN_ID_MIN}~{LOGIN_ID_MAX}자로 만들어 주세요.")
        if not _LOGIN_ID_RE.fullmatch(value):
            raise _invalid(
                "login_id", "아이디는 영문 소문자, 숫자, 점(.), 밑줄(_), 하이픈(-)만 쓸 수 있어요."
            )
        return value

    @field_validator("password")
    @classmethod
    def _password(cls, value: str) -> str:
        if not PASSWORD_MIN <= len(value) <= PASSWORD_MAX:
            raise _invalid("password", f"비밀번호는 {PASSWORD_MIN}~{PASSWORD_MAX}자로 만들어 주세요.")
        if not (_HAS_LETTER.search(value) and _HAS_DIGIT.search(value)):
            raise _invalid("password", "비밀번호에는 영문과 숫자가 하나 이상 들어가야 해요.")
        return value

    @field_validator("nickname")
    @classmethod
    def _nickname(cls, value: str | None) -> str | None:
        value = value.strip() if value is not None else None
        if not value:
            return None  # the service falls back to the login id
        if len(value) > NICKNAME_MAX:
            raise _invalid("nickname", f"닉네임은 {NICKNAME_MAX}자까지 쓸 수 있어요.")
        return value


class LoginBody(BaseModel):
    login_id: str
    password: str

    @field_validator("login_id")
    @classmethod
    def _login_id(cls, value: str) -> str:
        value = normalize_login_id(value)
        if not value or len(value) > _LOGIN_INPUT_MAX:
            raise _invalid("login_id", "아이디를 입력해 주세요.")
        return value

    @field_validator("password")
    @classmethod
    def _password(cls, value: str) -> str:
        if not value or len(value) > _LOGIN_INPUT_MAX:
            raise _invalid("password", "비밀번호를 입력해 주세요.")
        return value


class UserOut(BaseModel):
    id: str
    email: str | None = None
    login_id: str | None = None  # id/password accounts only
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
