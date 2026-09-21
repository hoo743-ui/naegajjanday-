"""RFC 9457 problem+json errors. `code` is the stable machine key the frontend switches on."""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    status: int = 500
    code: str = "INTERNAL_ERROR"
    title: str = "서버에 문제가 생겼어요"

    def __init__(
        self,
        detail: str | None = None,
        *,
        meta: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(detail or self.title)
        self.detail = detail
        self.meta = meta
        self.headers = headers


class BadRequest(AppError):
    status, code, title = 400, "BAD_REQUEST", "요청을 이해하지 못했어요"


class ValidationFailed(AppError):
    status, code, title = 422, "VALIDATION_ERROR", "입력값을 확인해 주세요"


class Unauthorized(AppError):
    status, code, title = 401, "UNAUTHORIZED", "로그인이 필요해요"


class TokenReuseDetected(Unauthorized):
    code, title = "TOKEN_REUSE_DETECTED", "보안을 위해 다시 로그인해 주세요"


class Forbidden(AppError):
    status, code, title = 403, "FORBIDDEN", "권한이 없어요"


class NotFound(AppError):
    status, code, title = 404, "NOT_FOUND", "찾을 수 없어요"


class RegionNotFound(NotFound):
    code, title = "REGION_NOT_FOUND", "아직 모르는 지역이에요"


class RegionNotReady(NotFound):
    code, title = "REGION_NOT_READY", "이 지역은 준비 중이에요"


class PurposeNotFound(NotFound):
    code, title = "PURPOSE_NOT_FOUND", "알 수 없는 목적이에요"


class CourseNotFound(NotFound):
    code, title = "COURSE_NOT_FOUND", "코스를 찾을 수 없어요"


class PlaceNotFound(NotFound):
    code, title = "PLACE_NOT_FOUND", "장소를 찾을 수 없어요"


class Conflict(AppError):
    status, code, title = 409, "CONFLICT", "이미 처리된 요청이에요"


class BudgetTooLow(AppError):
    status, code, title = 422, "BUDGET_TOO_LOW", "예산이 너무 낮아요"


class NoCourseAvailable(AppError):
    status, code, title = 422, "NO_COURSE_AVAILABLE", "조건에 맞는 코스를 만들지 못했어요"


class SwapNotPossible(AppError):
    status, code, title = 422, "SWAP_NOT_POSSIBLE", "바꿀 만한 장소를 찾지 못했어요"


class RateLimited(AppError):
    status, code, title = 429, "RATE_LIMITED", "요청이 너무 많아요. 잠시 후 다시 시도해 주세요"


class NotImplementedYet(AppError):
    status, code, title = 501, "NOT_IMPLEMENTED", "아직 준비 중인 기능이에요"


class ServiceUnavailable(AppError):
    status, code, title = 503, "SERVICE_UNAVAILABLE", "지금은 이용할 수 없어요"


class LLMUnavailable(ServiceUnavailable):
    code, title = "LLM_UNAVAILABLE", "짠이가 잠시 자리를 비웠어요"


class OAuthNotConfigured(ServiceUnavailable):
    code, title = "OAUTH_NOT_CONFIGURED", "이 로그인 방식은 아직 설정되지 않았어요"


def problem_body(
    *,
    type_base: str,
    status: int,
    code: str,
    title: str,
    detail: str | None,
    trace_id: str | None,
    meta: dict[str, Any] | None = None,
    errors: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "type": f"{type_base}/{code.lower().replace('_', '-')}",
        "title": title,
        "status": status,
        "code": code,
    }
    if detail:
        body["detail"] = detail
    if meta:
        body["meta"] = meta
    if errors:
        body["errors"] = errors
    body["trace_id"] = trace_id
    return body
