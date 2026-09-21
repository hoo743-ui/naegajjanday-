"""OpenAI Chat Completions over REST (httpx) — tools, JSON-schema output, SSE streaming."""

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

PROVIDER_NAME = "openai"
_STOP_REASONS = {
    "stop": "end_turn",
    "length": "max_tokens",
    "tool_calls": "tool_use",
    "content_filter": "refusal",
}


def to_openai_messages(messages: list[LLMMessage], system: str | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [{"role": "system", "content": system}] if system else []
    for msg in messages:
        if msg.role == "user":
            out.append({"role": "user", "content": msg.content})
        elif msg.role == "assistant":
            item: dict[str, Any] = {"role": "assistant", "content": msg.content or None}
            if msg.tool_calls:
                item["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                        },
                    }
                    for tc in msg.tool_calls
                ]
            out.append(item)
        else:
            out += [
                {"role": "tool", "tool_call_id": tr.tool_call_id, "content": tr.content}
                for tr in msg.tool_results
            ]
    return out


def build_payload(request: LLMRequest, model: str, *, stream: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": to_openai_messages(request.messages, request.system),
        "max_completion_tokens": request.max_tokens,
    }
    if request.tools:
        payload["tools"] = [
            {
                "type": "function",
                "function": {"name": t.name, "description": t.description, "parameters": t.input_schema},
            }
            for t in request.tools
        ]
    if request.json_schema is not None:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "out", "strict": True, "schema": request.json_schema},
        }
    if stream:
        payload["stream"] = True
        payload["stream_options"] = {"include_usage": True}
    return payload


def _parse_arguments(raw: str | None) -> dict[str, Any]:
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


class OpenAIProvider:
    name = PROVIDER_NAME

    def __init__(
        self,
        api_key: str | None,
        model_smart: str,
        model_fast: str,
        base_url: str = "https://api.openai.com/v1",
        *,
        timeout_s: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._models: dict[ModelTier, str] = {"smart": model_smart, "fast": model_fast}
        self._base_url = base_url.rstrip("/")
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
            raise LLMNotConfiguredError("OPENAI_API_KEY is not set")
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}

    async def complete(self, request: LLMRequest) -> LLMResponse:
        http = self._http()
        payload = build_payload(request, self.model_for(request.tier), stream=False)
        try:
            resp = await http.post(
                f"{self._base_url}/chat/completions", json=payload, headers=self._headers()
            )
        except httpx.HTTPError as exc:
            raise LLMError(f"openai connection error: {exc}", retryable=True) from exc
        _raise_for_status(resp)
        body = resp.json()
        choice = body["choices"][0]
        message = choice.get("message") or {}
        if message.get("refusal"):
            raise LLMRefusalError(str(message["refusal"]))
        tool_calls = [
            ToolCall(
                id=str(tc["id"]),
                name=str(tc["function"]["name"]),
                arguments=_parse_arguments(tc["function"].get("arguments")),
            )
            for tc in message.get("tool_calls") or []
        ]
        return _response(
            body.get("model"), message.get("content"), choice.get("finish_reason"), tool_calls, body
        )

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamEvent]:
        http = self._http()
        model = self.model_for(request.tier)
        payload = build_payload(request, model, stream=True)
        texts: list[str] = []
        calls: dict[int, dict[str, str]] = {}
        finish: str | None = None
        last_chunk: dict[str, Any] = {}
        try:
            async with http.stream(
                "POST", f"{self._base_url}/chat/completions", json=payload, headers=self._headers()
            ) as resp:
                if resp.status_code >= 400:
                    await resp.aread()
                    _raise_for_status(resp)
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    chunk = json.loads(data)
                    if chunk.get("usage"):
                        last_chunk = chunk
                    for choice in chunk.get("choices", []):
                        delta = choice.get("delta") or {}
                        if delta.get("content"):
                            texts.append(delta["content"])
                            yield LLMStreamEvent(type="token", text=delta["content"])
                        for tc in delta.get("tool_calls") or []:
                            slot = calls.setdefault(
                                int(tc.get("index", 0)), {"id": "", "name": "", "arguments": ""}
                            )
                            fn = tc.get("function") or {}
                            slot["id"] = tc.get("id") or slot["id"]
                            slot["name"] = fn.get("name") or slot["name"]
                            slot["arguments"] += fn.get("arguments") or ""
                        finish = choice.get("finish_reason") or finish
        except httpx.HTTPError as exc:
            raise LLMError(f"openai connection error: {exc}", retryable=True) from exc
        if finish == "content_filter":
            raise LLMRefusalError("openai content filter stopped the response")
        tool_calls = [
            ToolCall(id=c["id"], name=c["name"], arguments=_parse_arguments(c["arguments"]))
            for _, c in sorted(calls.items())
        ]
        yield LLMStreamEvent(
            type="final", response=_response(model, "".join(texts), finish, tool_calls, last_chunk)
        )

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


def _response(
    model: Any, text: str | None, finish: str | None, tool_calls: list[ToolCall], body: dict[str, Any]
) -> LLMResponse:
    usage = body.get("usage") or {}
    stop_reason = _STOP_REASONS.get(finish or "stop", finish or "end_turn")
    if stop_reason == "refusal":
        raise LLMRefusalError("openai content filter stopped the response")
    return LLMResponse(
        text=text or "",
        model=str(model or ""),
        stop_reason=stop_reason,
        tool_calls=tool_calls,
        usage=LLMUsage(
            tokens_in=int(usage.get("prompt_tokens") or 0),
            tokens_out=int(usage.get("completion_tokens") or 0),
        ),
    )


def _raise_for_status(resp: httpx.Response) -> None:
    if resp.status_code < 400:
        return
    try:
        detail = resp.json().get("error", {}).get("message", "")
    except (ValueError, AttributeError):
        detail = resp.text[:200]
    retryable = resp.status_code == 429 or resp.status_code >= 500
    raise LLMError(f"openai API error {resp.status_code}: {detail}", retryable=retryable)
