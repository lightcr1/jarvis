from __future__ import annotations

from .openai_compat import OpenAICompatibleProvider
from .base import ModelInfo
from ..model_router import Tier

# Static fallback model list (used when the API is unreachable or in tests)
_FALLBACK_MODELS = [
    ModelInfo("openrouter/free", "OpenRouter Free", Tier.SIMPLE, 0.0, 0.0),
    ModelInfo("anthropic/claude-haiku-4-5", "Claude Haiku 4.5 (OR)", Tier.SIMPLE, 1.0, 5.0),
    ModelInfo("anthropic/claude-sonnet-4-6", "Claude Sonnet 4.6 (OR)", Tier.MEDIUM, 3.0, 15.0),
    ModelInfo("anthropic/claude-opus-4-8", "Claude Opus 4.8 (OR)", Tier.COMPLEX, 5.0, 25.0),
    ModelInfo("openai/gpt-4o-mini", "GPT-4o Mini (OR)", Tier.SIMPLE, 0.15, 0.6),
    ModelInfo("openai/gpt-4o", "GPT-4o (OR)", Tier.MEDIUM, 2.5, 10.0),
    ModelInfo("google/gemini-2.0-flash", "Gemini 2.0 Flash (OR)", Tier.SIMPLE, 0.1, 0.4),
    ModelInfo("mistralai/mistral-large", "Mistral Large (OR)", Tier.MEDIUM, 2.0, 6.0),
    ModelInfo("deepseek/deepseek-chat", "DeepSeek Chat (OR)", Tier.MEDIUM, 0.14, 0.28),
]


class OpenRouterProvider(OpenAICompatibleProvider):
    name = "openrouter"
    base_url = "https://openrouter.ai/api/v1"
    _env_key_var = "OPENROUTER_API_KEY"
    supports_streaming = True

    def list_models(self) -> list[ModelInfo]:
        return list(_FALLBACK_MODELS)

    def validate_api_key(self, api_key: str) -> tuple[bool, str]:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key, base_url=self.base_url, timeout=10.0, max_retries=0)
            client.models.list()
            return True, "ok"
        except Exception as exc:
            return False, str(exc)
