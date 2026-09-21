from __future__ import annotations

from app.core.config import Settings
from app.infra.llm.base import LLMProvider
from app.infra.llm.fallback import NullProvider


def build_llm(settings: Settings) -> LLMProvider:
    """LLM_PROVIDER selects the vendor; without a key the null provider keeps the app fully functional."""
    name = settings.llm_provider
    if name == "anthropic" and settings.anthropic_api_key:
        from app.infra.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider(
            settings.anthropic_api_key,
            model_smart=settings.anthropic_model_smart,
            model_fast=settings.anthropic_model_fast,
            server_fallbacks=settings.anthropic_server_fallbacks,
            timeout_s=settings.llm_timeout_s,
        )
    if name == "openai" and settings.openai_api_key:
        from app.infra.llm.openai_provider import OpenAIProvider

        return OpenAIProvider(
            settings.openai_api_key,
            settings.openai_model_smart,
            settings.openai_model_fast,
            timeout_s=settings.llm_timeout_s,
        )
    if name == "gemini" and settings.gemini_api_key:
        from app.infra.llm.gemini_provider import GeminiProvider

        return GeminiProvider(
            settings.gemini_api_key,
            settings.gemini_model_smart,
            settings.gemini_model_fast,
            timeout_s=settings.llm_timeout_s,
        )
    return NullProvider()
