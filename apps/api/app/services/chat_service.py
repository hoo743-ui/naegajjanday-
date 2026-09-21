"""짠이 chatbot (doc 03 §6). The model can only act through tools, so it cannot invent places.

SSE events: token · tool_call · course · done · error
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import ValidationError
from sqlalchemy import select

from app.core import errors
from app.core.deps import Container
from app.core.logging import get_logger
from app.core.sse import sse
from app.infra.db.models import ChatMessage, ChatSession, Purpose, Region, User
from app.infra.llm.base import LLMError, LLMMessage, LLMRequest, LLMResponse, ToolCall, ToolResult, ToolSpec
from app.schemas.course import CourseGenerateRequest, SwapRequest
from app.services.factory import build_course_service
from app.services.place_service import PlaceService

logger = get_logger(__name__)

MAX_TOOL_ROUNDS = 5
HISTORY_LIMIT = 20

TOOLS: list[ToolSpec] = [
    ToolSpec(
        name="generate_course",
        description=(
            "예산·인원·지역·목적으로 코스를 생성한다. 사용자가 코스/일정/어디 갈지 추천을 원할 때 호출한다. "
            "region 은 시스템 프롬프트의 지원 지역 slug, purpose 는 지원 목적 code 중 하나여야 한다."
        ),
        input_schema={
            "type": "object",
            "additionalProperties": False,
            "required": ["region", "purpose", "party_size", "budget_total"],
            "properties": {
                "region": {"type": "string", "description": "지역 slug"},
                "purpose": {"type": "string", "description": "목적 code"},
                "party_size": {"type": "integer", "minimum": 1, "maximum": 20},
                "budget_total": {"type": "integer", "description": "총 예산(원)"},
                "start_at": {"type": "string", "description": "ISO-8601 시작 시각. 모르면 생략(현재)"},
                "transport": {"type": "string", "enum": ["walk", "transit", "car"]},
                "liked_tags": {"type": "array", "items": {"type": "string"}},
                "disliked_tags": {"type": "array", "items": {"type": "string"}},
            },
        },
    ),
    ToolSpec(
        name="search_places",
        description="이름·키워드로 승인된 장소를 검색한다. 특정 가게나 종류를 찾을 때 호출한다.",
        input_schema={
            "type": "object",
            "additionalProperties": False,
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
                "region": {"type": "string", "description": "지역 slug"},
                "role": {
                    "type": "string",
                    "description": "MEAL, CAFE, DESSERT, ATTRACTION, ACTIVITY, CULTURE, BAR, NIGHTVIEW",
                },
                "max_price": {"type": "integer", "description": "1인 최대 금액(원)"},
            },
        },
    ),
    ToolSpec(
        name="swap_stop",
        description="이미 만든 코스에서 한 곳만 다른 장소로 바꾼다. course_id 는 generate_course 결과의 id.",
        input_schema={
            "type": "object",
            "additionalProperties": False,
            "required": ["course_id", "position", "strategy"],
            "properties": {
                "course_id": {"type": "string"},
                "position": {"type": "integer", "minimum": 1},
                "strategy": {"type": "string", "enum": ["cheaper", "closer", "higher_rated", "random_top"]},
            },
        },
    ),
    ToolSpec(
        name="get_events",
        description="지역에서 특정 날짜에 진행 중인 축제·전시·공연을 조회한다.",
        input_schema={
            "type": "object",
            "additionalProperties": False,
            "required": ["region"],
            "properties": {
                "region": {"type": "string", "description": "지역 slug"},
                "date": {"type": "string", "description": "YYYY-MM-DD. 생략 시 오늘"},
            },
        },
    ),
]


def _course_digest(course: dict[str, Any]) -> dict[str, Any]:
    """What the model sees of a course: facts only, small enough to keep the context lean."""
    return {
        "id": course["id"],
        "label": course["label"],
        "totals": {k: course["totals"][k] for k in ("price", "budget_left", "travel_min", "duration_min")},
        "stops": [
            {
                "position": s["position"],
                "role": s["role"],
                "name": s["place"]["name"],
                "est_price": s["est_price"],
                "arrive_at": s["arrive_at"],
            }
            for s in course["stops"]
        ],
        "warnings": [w["code"] for w in course.get("warnings", [])],
    }


class ChatService:
    def __init__(self, container: Container) -> None:
        self._c = container
        self._tz = ZoneInfo(container.settings.timezone)

    def ensure_available(self) -> None:
        if not self._c.llm.available:
            raise errors.LLMUnavailable("챗봇을 쓰려면 LLM_PROVIDER 와 API 키 설정이 필요해요.")

    async def create_session(self, user: User | None) -> str:
        async with self._c.db.sessionmaker() as s:
            row = ChatSession(user_id=user.id if user else None, context={})
            s.add(row)
            await s.commit()
            return row.public_id

    async def _session_id(self, public_id: str, user: User | None) -> int:
        async with self._c.db.sessionmaker() as s:
            row = await s.scalar(select(ChatSession).where(ChatSession.public_id == public_id))
            if row is None:
                raise errors.NotFound("대화를 찾을 수 없어요.")
            if row.user_id is not None and (user is None or user.id != row.user_id):
                raise errors.Forbidden()
            return row.id

    async def _system_prompt(self) -> str:
        async with self._c.db.sessionmaker() as s:
            regions = (
                await s.execute(
                    select(Region.slug, Region.name).where(Region.status == "active", Region.level == 3)
                )
            ).all()
            purposes = (
                await s.execute(select(Purpose.code, Purpose.name).where(Purpose.is_active.is_(True)))
            ).all()
        rendered = self._c.prompts.get("chat_system").render(
            regions=[f"{name}({slug})" for slug, name in regions],
            purposes=[f"{name}({code})" for code, name in purposes],
            now=datetime.now(self._tz).isoformat(timespec="minutes"),
        )
        return rendered.system

    async def prepare(self, session_public_id: str, user: User | None) -> int:
        """Everything that can fail with a problem response happens before the stream starts."""
        self.ensure_available()
        return await self._session_id(session_public_id, user)

    async def stream_reply(self, session_id: int, content: str, user: User | None) -> AsyncIterator[str]:
        async with self._c.db.sessionmaker() as s:
            rows = (
                await s.scalars(
                    select(ChatMessage)
                    .where(ChatMessage.session_id == session_id, ChatMessage.role.in_(["user", "assistant"]))
                    .order_by(ChatMessage.id.desc())
                    .limit(HISTORY_LIMIT)
                )
            ).all()
            s.add(ChatMessage(session_id=session_id, role="user", content=content, tool_calls=[]))
            await s.commit()
        messages = [LLMMessage(role=r.role, content=r.content) for r in reversed(rows) if r.content]  # type: ignore[arg-type]
        messages.append(LLMMessage(role="user", content=content))
        system = await self._system_prompt()
        max_tokens = self._c.prompts.get("chat_system").max_tokens

        text_parts: list[str] = []
        calls_log: list[dict[str, Any]] = []
        tokens_in = tokens_out = 0
        model = self._c.llm.model_for("smart")
        try:
            for _round in range(MAX_TOOL_ROUNDS):
                final: LLMResponse | None = None
                request = LLMRequest(
                    messages=messages, system=system, tools=TOOLS, tier="smart", max_tokens=max_tokens
                )
                async for event in self._c.llm.stream(request):
                    if event.type == "token" and event.text:
                        text_parts.append(event.text)
                        yield sse("token", {"text": event.text})
                    elif event.type == "final":
                        final = event.response
                if final is None:
                    break
                tokens_in += final.usage.tokens_in
                tokens_out += final.usage.tokens_out
                model = final.model
                if not final.tool_calls:
                    break
                messages.append(final.as_message())
                results: list[ToolResult] = []
                for call in final.tool_calls:
                    yield sse("tool_call", {"name": call.name, "arguments": call.arguments})
                    result, card = await self._run_tool(call, user)
                    calls_log.append(
                        {"name": call.name, "arguments": call.arguments, "is_error": result.is_error}
                    )
                    if card is not None:
                        yield sse("course", card)
                    results.append(result)
                messages.append(LLMMessage(role="tool", tool_results=results))  # all results in ONE message
            yield sse("done", {"tokens_in": tokens_in, "tokens_out": tokens_out})
        except LLMError as exc:
            logger.warning("chat.llm_failed", error=str(exc))
            yield sse("error", {"code": "LLM_UNAVAILABLE", "retryable": exc.retryable})
        finally:
            async with self._c.db.sessionmaker() as s:
                s.add(
                    ChatMessage(
                        session_id=session_id,
                        role="assistant",
                        content="".join(text_parts),
                        tool_calls=calls_log,
                        tokens_in=tokens_in,
                        tokens_out=tokens_out,
                        model=model,
                    )
                )
                await s.commit()

    async def _run_tool(self, call: ToolCall, user: User | None) -> tuple[ToolResult, dict[str, Any] | None]:
        """Tool inputs come from the model: validate them with the same DTOs as the public API."""
        args = call.arguments
        try:
            async with self._c.db.sessionmaker() as s:
                if call.name == "generate_course":
                    prefs = {
                        "liked_tags": args.pop("liked_tags", []),
                        "disliked_tags": args.pop("disliked_tags", []),
                    }
                    req = CourseGenerateRequest.model_validate(
                        {**args, "preferences": prefs, "alternatives": 0}
                    )
                    resp = await build_course_service(self._c, s).generate(req, user)
                    card = resp.courses[0].model_dump(mode="json")
                    return self._ok(call, _course_digest(card)), card
                if call.name == "swap_stop":
                    body = SwapRequest(position=args["position"], strategy=args["strategy"])
                    out = await build_course_service(self._c, s).swap(str(args["course_id"]), body, user)
                    card = out.model_dump(mode="json")
                    return self._ok(call, _course_digest(card)), card
                places = PlaceService(self._c.settings, s, self._c.search)
                if call.name == "search_places":
                    found = await places.search(
                        q=str(args["query"]), region=args.get("region"), role=args.get("role"),
                        max_price=args.get("max_price"), lat=None, lng=None, radius=None,
                        sort="relevance", limit=8, offset=0,
                    )  # fmt: skip
                    keep = {"id", "name", "category", "price_per_person", "rating", "tags"}
                    items = [i.model_dump(include=keep) for i in found.items]
                    return self._ok(call, {"items": items}), None
                if call.name == "get_events":
                    day = datetime.fromisoformat(args["date"]).date() if args.get("date") else None
                    events = await places.events(str(args["region"]), day, day)
                    return self._ok(call, events.model_dump(mode="json")), None
            return ToolResult(call.id, f"unknown tool: {call.name}", is_error=True, name=call.name), None
        except errors.AppError as exc:
            payload = {"code": exc.code, "title": exc.title, "detail": exc.detail, "meta": exc.meta}
            return ToolResult(
                call.id, json.dumps(payload, ensure_ascii=False), is_error=True, name=call.name
            ), None
        except (ValidationError, KeyError, ValueError, TypeError) as exc:
            return ToolResult(call.id, f"INVALID_ARGUMENTS: {exc}", is_error=True, name=call.name), None

    @staticmethod
    def _ok(call: ToolCall, payload: dict[str, Any]) -> ToolResult:
        return ToolResult(call.id, json.dumps(payload, ensure_ascii=False, default=str), name=call.name)
