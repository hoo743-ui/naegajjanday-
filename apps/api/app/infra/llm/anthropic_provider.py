"""Claude via the official `anthropic` SDK (1.x, AsyncAnthropic).

Notes (see Anthropic docs): model ids carry no date suffix; no `temperature`, no assistant prefill,
no `budget_tokens`. Opus/Sonnet/Fable-family models think adaptively by default, so `thinking` is
omitted and depth is controlled with `output_config.effort`; the fast (Haiku) tier gets neither.
Assistant content is echoed back unchanged (`provider_state`) so thinking blocks stay valid.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import anthropic
from anthropic import AsyncAnthropic

from app.infra.llm.base import (
    LLMError,
    LLMMessage,
    LLMNotConfiguredError,
    LLMRefusalError,
    LLMRequest,
    LLMResponse,
    LLMStreamEvent,
    LLMUsage,
    ModelTier,
    ToolCall,
)

PROVIDER_NAME = "anthropic"
FALLBACK_BETA = "server-side-fallback-2026-07-01"  # pairs with the scalar form `fallbacks="default"`
_EFFORT_PREFIXES: tuple[str, ...] = (
    "claude-opus-5",
    "claude-opus-4-8",
    "claude-opus-4-7",
    "claude-opus-4-6",
    "claude-sonnet-5",
    "claude-sonnet-4-6",
    "claude-fable",
)
_FALLBACK_PREFIXES: tuple[str, ...] = ("claude-opus-5", "claude-fable")


def _supports_effort(model: str) -> bool:
    return model.startswith(_EFFORT_PREFIXES)


def _supports_server_fallbacks(model: str) -> bool:
    return model.startswith(_FALLBACK_PREFIXES)


def to_anthropic_messages(messages: list[LLMMessage]) -> list[dict[str, Any]]:
    """Neutral messages → Anthropic `messages`. All tool results of a turn go in ONE user message."""
    out: list[dict[str, Any]] = []
    for msg in messages:
        if msg.role == "user":
            out.append({"role": "user", "content": msg.content})
        elif msg.role == "assistant":
            state = msg.provider_state
            if isinstance(state, dict) and state.get("provider") == PROVIDER_NAME:
                out.append({"role": "assistant", "content": state["content"]})
                continue
            blocks: list[dict[str, Any]] = []
            if msg.content:
                blocks.append({"type": "text", "text": msg.content})
            blocks += [
                {"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.arguments}
                for tc in msg.tool_calls
            ]
            if blocks:
                out.append({"role": "assistant", "content": blocks})
        else:  # "tool"
            results: list[dict[str, Any]] = []
            for tr in msg.tool_results:
                block: dict[str, Any] = {
                    "type": "tool_result",
                    "tool_use_id": tr.tool_call_id,
                    "content": tr.content,
                }
                if tr.is_error:
                    block["is_error"] = True
                results.append(block)
            if results:
                out.append({"role": "user", "content": results})
    return out


def build_request_kwargs(request: LLMRequest, model: str) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": request.max_tokens,
        "messages": to_anthropic_messages(request.messages),
    }
    if request.system:
        kwargs["system"] = request.system
    if request.tools:
        kwargs["tools"] = [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema}
            for t in request.tools
        ]
    output_config: dict[str, Any] = {}
    if _supports_effort(model):
        output_config["effort"] = "low"  # narrative/chat are latency-sensitive, low-complexity
    if request.json_schema is not None:
        output_config["format"] = {"type": "json_schema", "schema": request.json_schema}
    if output_config:
        kwargs["output_config"] = output_config
    return kwargs


class AnthropicProvider:
    name = PROVIDER_NAME

    def __init__(
        self,
        api_key: str | None,
        model_smart: str = "claude-opus-5",
        model_fast: str = "claude-haiku-4-5",
        server_fallbacks: bool = True,
        timeout_s: float = 30.0,
    ) -> None:
        self._api_key = api_key
        self._models: dict[ModelTier, str] = {"smart": model_smart, "fast": model_fast}
        self._server_fallbacks = server_fallbacks
        self._timeout_s = timeout_s
        self._client: AsyncAnthropic | None = None

    @property
    def available(self) -> bool:
        return bool(self._api_key)

    def model_for(self, tier: ModelTier) -> str:
        return self._models[tier]

    def _get_client(self) -> AsyncAnthropic:
        if not self._api_key:
            raise LLMNotConfiguredError("ANTHROPIC_API_KEY is not set")
        if self._client is None:
            self._client = AsyncAnthropic(api_key=self._api_key, timeout=self._timeout_s, max_retries=2)
        return self._client

    def _use_fallbacks(self, model: str) -> bool:
        return self._server_fallbacks and _supports_server_fallbacks(model)

    async def complete(self, request: LLMRequest) -> LLMResponse:
        client = self._get_client()
        model = self.model_for(request.tier)
        kwargs = build_request_kwargs(request, model)
        try:
            if self._use_fallbacks(model):
                message: Any = await client.beta.messages.create(
                    **kwargs, betas=[FALLBACK_BETA], fallbacks="default"
                )
            else:
                message = await client.messages.create(**kwargs)
        except anthropic.APIError as exc:
            raise _translate_error(exc) from exc
        return _to_response(message)

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamEvent]:
        client = self._get_client()
        model = self.model_for(request.tier)
        kwargs = build_request_kwargs(request, model)
        try:
            if self._use_fallbacks(model):
                manager: Any = client.beta.messages.stream(
                    **kwargs, betas=[FALLBACK_BETA], fallbacks="default"
                )
            else:
                manager = client.messages.stream(**kwargs)
            async with manager as stream:
                async for text in stream.text_stream:
                    yield LLMStreamEvent(type="token", text=text)
                message = await stream.get_final_message()
        except anthropic.APIError as exc:
            raise _translate_error(exc) from exc
        yield LLMStreamEvent(type="final", response=_to_response(message))

    async def complete_json(self, request: LLMRequest) -> dict[str, Any]:
        if request.json_schema is None:
            raise ValueError("complete_json requires request.json_schema")
        response = await self.complete(request)
        if response.stop_reason == "max_tokens":
            raise LLMError("structured output was truncated (max_tokens)", retryable=False)
        try:
            data = json.loads(response.text)
        except json.JSONDecodeError as exc:
            raise LLMError(f"model returned invalid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise LLMError("structured output must be a JSON object")
        return data

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None


def _to_response(message: Any) -> LLMResponse:
    stop_reason = str(message.stop_reason or "end_turn")
    if stop_reason == "refusal":
        details = getattr(message, "stop_details", None)
        category = getattr(details, "category", None)
        raise LLMRefusalError(f"model declined the request (category={category})")
    texts: list[str] = []
    tool_calls: list[ToolCall] = []
    for block in message.content:
        if block.type == "text":
            texts.append(block.text)
        elif block.type == "tool_use":
            arguments = block.input if isinstance(block.input, dict) else {}
            tool_calls.append(ToolCall(id=block.id, name=block.name, arguments=dict(arguments)))
    usage = message.usage
    return LLMResponse(
        text="".join(texts),
        model=str(message.model),
        stop_reason=stop_reason,
        tool_calls=tool_calls,
        usage=LLMUsage(tokens_in=int(usage.input_tokens or 0), tokens_out=int(usage.output_tokens or 0)),
        provider_state={"provider": PROVIDER_NAME, "content": list(message.content)},
    )


def _translate_error(exc: anthropic.APIError) -> LLMError:
    # most specific first: 429 → other HTTP status → transport
    if isinstance(exc, anthropic.RateLimitError):
        return LLMError(f"anthropic rate limited: {exc.message}", retryable=True)
    if isinstance(exc, anthropic.APIStatusError):
        return LLMError(
            f"anthropic API error {exc.status_code}: {exc.message}", retryable=exc.status_code >= 500
        )
    if isinstance(exc, anthropic.APIConnectionError):
        return LLMError(f"anthropic connection error: {exc}", retryable=True)
    return LLMError(f"anthropic unexpected error: {exc}")
