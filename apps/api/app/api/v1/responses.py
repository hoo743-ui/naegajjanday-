"""OpenAPI documentation of problem+json error responses."""

from __future__ import annotations

from typing import Any

from app.schemas.common import Problem

_DESCRIPTIONS = {
    400: "Bad request",
    401: "인증 필요",
    403: "권한 없음",
    404: "리소스 없음 (REGION_NOT_FOUND, REGION_NOT_READY, COURSE_NOT_FOUND …)",
    409: "충돌",
    422: "검증 실패 또는 도메인 오류 (BUDGET_TOO_LOW, NO_COURSE_AVAILABLE …)",
    429: "Rate limit 초과 (Retry-After 헤더)",
    501: "아직 구현되지 않음 (NOT_IMPLEMENTED)",
    503: "의존 서비스 미설정/장애",
}


def PROBLEMS(*statuses: int) -> dict[int | str, dict[str, Any]]:
    return {
        status: {
            "model": Problem,
            "description": _DESCRIPTIONS.get(status, "Error"),
            "content": {"application/problem+json": {}},
        }
        for status in statuses
    }
