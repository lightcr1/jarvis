from __future__ import annotations

from .openai_compat import OpenAICompatibleProvider
from .base import ModelInfo
from ..model_router import Tier

_FALLBACK_MODELS = [
    ModelInfo("deepseek-chat", "DeepSeek Chat", Tier.SIMPLE, 0.14, 0.28),
    ModelInfo("deepseek-reasoner", "DeepSeek Reasoner", Tier.COMPLEX, 0.55, 2.19),
]


class DeepSeekProvider(OpenAICompatibleProvider):
    name = "deepseek"
    base_url = "https://api.deepseek.com"
    _env_key_var = "DEEPSEEK_API_KEY"
    supports_streaming = True

    def list_models(self) -> list[ModelInfo]:
        return list(_FALLBACK_MODELS)
