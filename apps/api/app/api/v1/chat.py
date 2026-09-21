from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.responses import PROBLEMS
from app.core.deps import ContainerDep, OptionalUser, rate_limit
from app.core.sse import SSE_HEADERS, with_heartbeat
from app.services.chat_service import ChatService

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatSessionOut(BaseModel):
    id: str


class ChatMessageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=1000, examples=["성수에서 3만원으로 혼밥하고 전시 볼래"])


@router.post(
    "/sessions",
    response_model=ChatSessionOut,
    status_code=201,
    dependencies=[Depends(rate_limit("read"))],
    responses=PROBLEMS(503),
)
async def create_session(container: ContainerDep, user: OptionalUser) -> ChatSessionOut:
    service = ChatService(container)
    service.ensure_available()
    return ChatSessionOut(id=await service.create_session(user))


@router.post(
    "/sessions/{session_id}/messages",
    dependencies=[Depends(rate_limit("chat"))],
    responses={200: {"content": {"text/event-stream": {}}}, **PROBLEMS(403, 404, 429, 503)},
    summary="SSE: token · tool_call · course · done · error",
)
async def post_message(
    session_id: str, body: ChatMessageIn, container: ContainerDep, user: OptionalUser
) -> StreamingResponse:
    service = ChatService(container)
    internal_id = await service.prepare(session_id, user)
    return StreamingResponse(
        with_heartbeat(service.stream_reply(internal_id, body.content, user)),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
