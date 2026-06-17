from __future__ import annotations

from .openai_compat import OpenAICompatibleProvider
from .base import ModelInfo
from ..model_router import Tier

_FALLBACK_MODELS = [
    ModelInfo("mistral-small-latest", "Mistral Small", Tier.SIMPLE, 0.2, 0.6),
    ModelInfo("mistral-medium-latest", "Mistral Medium", Tier.MEDIUM, 2.7, 8.1),
    ModelInfo("mistral-large-latest", "Mistral Large", Tier.COMPLEX, 2.0, 6.0),
]


class MistralProvider(OpenAICompatibleProvider):
    name = "mistral"
    base_url = "https://api.mistral.ai/v1"
    _env_key_var = "MISTRAL_API_KEY"
    supports_streaming = True

    def list_models(self) -> list[ModelInfo]:
        return list(_FALLBACK_MODELS)
