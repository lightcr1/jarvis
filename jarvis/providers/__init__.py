from .base import AIProvider, BaseProvider, ChatChunk, ChatResult, ModelInfo

_REGISTRY: dict[str, type] = {}


def _register(name: str, cls: type) -> None:
    _REGISTRY[name] = cls


def get_provider_instance(name: str, *, api_key: str | None = None, **kwargs) -> "AIProvider":
    from .anthropic_provider import AnthropicProvider
    from .openai_provider import OpenAIProvider
    from .gemini_provider import GeminiProvider
    from .local_provider import LocalProvider
    from .openrouter_provider import OpenRouterProvider
    from .mistral_provider import MistralProvider
    from .deepseek_provider import DeepSeekProvider

    providers = {
        "anthropic": AnthropicProvider,
        "openai": OpenAIProvider,
        "gemini": GeminiProvider,
        "local": LocalProvider,
        "openrouter": OpenRouterProvider,
        "mistral": MistralProvider,
        "deepseek": DeepSeekProvider,
    }
    cls = providers.get(name)
    if cls is None:
        raise ValueError(f"Unknown provider: {name!r}")
    return cls(api_key=api_key, **kwargs)


__all__ = [
    "AIProvider",
    "BaseProvider",
    "ChatChunk",
    "ChatResult",
    "ModelInfo",
    "get_provider_instance",
]
