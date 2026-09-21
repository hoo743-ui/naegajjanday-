"""Google Gemini `generateContent` over REST (httpx) — function calling, response schema, SSE streaming."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

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

PROVIDER_NAME = "gemini"
BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
_UNSUPPORTED_SCHEMA_KEYS = frozenset({"additionalProperties", "$schema", "$id", "strict"})
_REFUSAL_REASONS = frozenset({"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "RECITATION"})


def sanitize_schema(schema: Any) -> Any:
    """Gemini's OpenAPI-subset schema rejects `additionalProperties` and friends — strip recursively."""
    if isinstance(schema, dict):
        return {k: sanitize_schema(v) for k, v in schema.items() if k not in _UNSUPPORTED_SCHEMA_KEYS}
    if isinstance(schema, list):
        return [sanitize_schema(v) for v in schema]
    return schema


def to_gemini_contents(messages: list[LLMMessage]) -> list[dict[str, Any]]:
    contents: list[dict[str, Any]] = []
    call_names: dict[str, str] = {}
    for msg in messages:
        if msg.role == "user":
            contents.append({"role": "user", "parts": [{"text": msg.content}]})
        elif msg.role == "assistant":
            for tc in msg.tool_calls:
                call_names[tc.id] = tc.name
            state = msg.provider_state
            if isinstance(state, dict) and state.get("provider") == PROVIDER_NAME:
                contents.append({"role": "model", "parts": state["content"]})  # keeps thoughtSignature
                continue
            parts: list[dict[str, Any]] = [{"text": msg.content}] if msg.content else []
            parts += [{"functionCall": {"name": tc.name, "args": tc.arguments}} for tc in msg.tool_calls]
            if parts:
                contents.append({"role": "model", "parts": parts})
        else:
            parts = []
            for tr in msg.tool_results:
                name = tr.name or call_names.get(tr.tool_call_id, tr.tool_call_id)
                key = "error" if tr.is_error else "result"
                parts.append({"functionResponse": {"name": name, "response": {key: tr.content}}})
            if parts:
                contents.append({"role": "user", "parts": parts})
    return contents


def build_payload(request: LLMRequest) -> dict[str, Any]:
    payload: dict[str, Any] = {"contents": to_gemini_contents(request.messages)}
    if request.system:
        payload["systemInstruction"] = {"parts": [{"text": request.system}]}
    if request.tools:
        payload["tools"] = [
            {
                "functionDeclarations": [
                    {
                        "name": t.name,
                        "description": t.description,
                        "parameters": sanitize_schema(t.input_schema),
                    }
                    for t in request.tools
                ]
            }
        ]
    generation: dict[str, Any] = {"maxOutputTokens": request.max_tokens}
    if request.json_schema is not None:
        generation["responseMimeType"] = "application/json"
        generation["responseSchema"] = sanitize_schema(request.json_schema)
    payload["generationConfig"] = generation
    return payload


class GeminiProvider:
    name = PROVIDER_NAME

    def __init__(
        self,
        api_key: str | None,
        model_smart: str,
        model_fast: str,
        *,
        timeout_s: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._models: dict[ModelTier, str] = {"smart": model_smart, "fast": model_fast}
        self._timeout = httpx.Timeout(timeout_s, connect=5.0)
        self._client = client
        self._owns_client = client is None

    @property
    def available(self) -> bool:
        return bool(self._api_key)

    def model_for(self, tier: ModelTier) -> str:
        return self._models[tier]

    def _http(self) -> httpx.AsyncClient:
        if not self._api_key:
            raise LLMNotConfiguredError("GEMINI_API_KEY is not set")
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    def _headers(self) -> dict[str, str]:
        return {"x-goog-api-key": self._api_key or "", "Content-Type": "application/json"}

    async def complete(self, request: LLMRequest) -> LLMResponse:
        http = self._http()
        model = self.model_for(request.tier)
        try:
            resp = await http.post(
                f"{BASE_URL}/models/{model}:generateContent",
                json=build_payload(request),
                headers=self._headers(),
            )
        except httpx.HTTPError as exc:
            raise LLMError(f"gemini connection error: {exc}", retryable=True) from exc
        _raise_for_status(resp)
        acc = _Accumulator(model)
        acc.add(resp.json())
        return acc.response()

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamEvent]:
        http = self._http()
        model = self.model_for(request.tier)
        acc = _Accumulator(model)
        try:
            async with http.stream(
                "POST",
                f"{BASE_URL}/models/{model}:streamGenerateContent",
                params={"alt": "sse"},
                json=build_payload(request),
                headers=self._headers(),
            ) as resp:
                if resp.status_code >= 400:
                    await resp.aread()
                    _raise_for_status(resp)
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    text = acc.add(json.loads(line[5:].strip()))
                    if text:
                        yield LLMStreamEvent(type="token", text=text)
        except httpx.HTTPError as exc:
            raise LLMError(f"gemini connection error: {exc}", retryable=True) from exc
        yield LLMStreamEvent(type="final", response=acc.response())

    async def complete_json(self, request: LLMRequest) -> dict[str, Any]:
        if request.json_schema is None:
            raise ValueError("complete_json requires request.json_schema")
        response = await self.complete(request)
        if response.stop_reason == "max_tokens":
            raise LLMError("structured output was truncated (max_tokens)")
        try:
            data = json.loads(response.text)
        except json.JSONDecodeError as exc:
            raise LLMError(f"model returned invalid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise LLMError("structured output must be a JSON object")
        return data

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None


class _Accumulator:
    """Folds one or many `GenerateContentResponse` chunks into a single neutral response."""

    def __init__(self, model: str) -> None:
        self.model = model
        self.parts: list[dict[str, Any]] = []
        self.texts: list[str] = []
        self.finish: str | None = None
        self.usage: dict[str, Any] = {}

    def add(self, chunk: dict[str, Any]) -> str:
        feedback = chunk.get("promptFeedback") or {}
        if feedback.get("blockReason"):
            raise LLMRefusalError(f"gemini blocked the prompt: {feedback['blockReason']}")
        self.usage = chunk.get("usageMetadata") or self.usage
        new_text: list[str] = []
        for candidate in chunk.get("candidates", [])[:1]:
            self.finish = candidate.get("finishReason") or self.finish
            for part in (candidate.get("content") or {}).get("parts", []):
                self.parts.append(part)
                if part.get("text") and not part.get("thought"):
                    new_text.append(part["text"])
        self.texts += new_text
        return "".join(new_text)

    def response(self) -> LLMResponse:
        if self.finish in _REFUSAL_REASONS:
            raise LLMRefusalError(f"gemini stopped the response: {self.finish}")
        tool_calls: list[ToolCall] = []
        for part in self.parts:
            call = part.get("functionCall")
            if call:
                call_id = str(call.get("id") or f"call_{len(tool_calls)}")
                tool_calls.append(
                    ToolCall(id=call_id, name=str(call.get("name", "")), arguments=call.get("args") or {})
                )
        if tool_calls:
            stop_reason = "tool_use"
        elif self.finish == "MAX_TOKENS":
            stop_reason = "max_tokens"
        else:
            stop_reason = "end_turn"
        return LLMResponse(
            text="".join(self.texts),
            model=self.model,
            stop_reason=stop_reason,
            tool_calls=tool_calls,
            usage=LLMUsage(
                tokens_in=int(self.usage.get("promptTokenCount") or 0),
                tokens_out=int(self.usage.get("candidatesTokenCount") or 0),
            ),
            provider_state={"provider": PROVIDER_NAME, "content": list(self.parts)},
        )


def _raise_for_status(resp: httpx.Response) -> None:
    if resp.status_code < 400:
        return
    try:
        detail = resp.json().get("error", {}).get("message", "")
    except (ValueError, AttributeError):
        detail = resp.text[:200]
    retryable = resp.status_code == 429 or resp.status_code >= 500
    raise LLMError(f"gemini API error {resp.status_code}: {detail}", retryable=retryable)
