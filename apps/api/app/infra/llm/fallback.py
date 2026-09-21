"""No-key behaviour: the null provider reports `available = False`; callers then use the template
narrative from the prompt layer. It never fabricates model output."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from app.infra.llm.base import LLMNotConfiguredError, LLMRequest, LLMResponse, LLMStreamEvent, ModelTier


class NullProvider:
    name = "none"

    @property
    def available(self) -> bool:
        return False

    def model_for(self, tier: ModelTier) -> str:
        return "none"

    async def complete(self, request: LLMRequest) -> LLMResponse:
        raise LLMNotConfiguredError("no LLM provider configured (set LLM_PROVIDER and its API key)")

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamEvent]:
        raise LLMNotConfiguredError("no LLM provider configured (set LLM_PROVIDER and its API key)")
        yield  # pragma: no cover  (makes this an async generator)

    async def complete_json(self, request: LLMRequest) -> dict[str, Any]:
        raise LLMNotConfiguredError("no LLM provider configured (set LLM_PROVIDER and its API key)")
