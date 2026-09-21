"""Provider-agnostic LLM contract. The LLM never scores places (doc 06 §0)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

ModelTier = Literal["fast", "smart"]  # fast = batch sentiment/tagging, smart = narrative/chat


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]  # JSON Schema (object, additionalProperties=false)


@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ToolResult:
    tool_call_id: str
    content: str
    is_error: bool = False
    name: str | None = None


@dataclass(slots=True)
class LLMMessage:
    role: Literal["user", "assistant", "tool"]
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)  # assistant turn
    tool_results: list[ToolResult] = field(default_factory=list)  # role == "tool"
    # Provider-native assistant content (e.g. Anthropic thinking blocks) echoed back unchanged.
    provider_state: Any = None


@dataclass(slots=True)
class LLMRequest:
    messages: list[LLMMessage]
    system: str | None = None
    tools: list[ToolSpec] = field(default_factory=list)
    tier: ModelTier = "smart"
    max_tokens: int = 4096
    json_schema: dict[str, Any] | None = None  # structured output


@dataclass(slots=True)
class LLMUsage:
    tokens_in: int = 0
    tokens_out: int = 0


@dataclass(slots=True)
class LLMResponse:
    text: str
    model: str
    stop_reason: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: LLMUsage = field(default_factory=LLMUsage)
    provider_state: Any = None

    def as_message(self) -> LLMMessage:
        return LLMMessage(
            role="assistant",
            content=self.text,
            tool_calls=self.tool_calls,
            provider_state=self.provider_state,
        )


@dataclass(frozen=True, slots=True)
class LLMStreamEvent:
    type: Literal["token", "final"]
    text: str = ""
    response: LLMResponse | None = None  # set on "final"


class LLMError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class LLMNotConfiguredError(LLMError):
    pass


class LLMRefusalError(LLMError):
    pass


@runtime_checkable
class LLMProvider(Protocol):
    name: str

    @property
    def available(self) -> bool: ...

    def model_for(self, tier: ModelTier) -> str: ...

    async def complete(self, request: LLMRequest) -> LLMResponse: ...

    def stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamEvent]:
        """Yield `token` events, then exactly one `final` event carrying the full response."""
        ...

    async def complete_json(self, request: LLMRequest) -> dict[str, Any]:
        """Structured output: `request.json_schema` is enforced natively by the provider."""
        ...
