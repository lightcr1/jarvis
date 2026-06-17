from __future__ import annotations

import os
from typing import Iterator

from .base import BaseProvider, ChatChunk, ChatResult, ModelInfo
from ..model_router import Tier, select_model, max_tokens_for

_MODELS = [
    ModelInfo("claude-haiku-4-5", "Claude Haiku 4.5", Tier.SIMPLE, 1.0, 5.0),
    ModelInfo("claude-sonnet-4-6", "Claude Sonnet 4.6", Tier.MEDIUM, 3.0, 15.0),
    ModelInfo("claude-opus-4-8", "Claude Opus 4.8", Tier.COMPLEX, 5.0, 25.0),
]


class AnthropicProvider(BaseProvider):
    name = "anthropic"
    supports_streaming = True

    def __init__(self, *, api_key: str | None = None, client_factory=None):
        self._api_key = api_key or os.getenv("ANTHROPIC_API_KEY") or ""
        self._client_factory = client_factory

    def _get_client(self):
        if self._client_factory is not None:
            return self._client_factory()
        import anthropic as _sdk
        return _sdk.Anthropic(api_key=self._api_key)

    def list_models(self) -> list[ModelInfo]:
        return list(_MODELS)

    def validate_api_key(self, api_key: str) -> tuple[bool, str]:
        try:
            import anthropic as _sdk
            client = _sdk.Anthropic(api_key=api_key)
            client.models.list()
            return True, "ok"
        except Exception as exc:
            return False, str(exc)

    def create_chat_completion(
        self,
        *,
        model: str,
        messages: list[dict],
        system_prompt: str,
        max_tokens: int,
        tier: Tier,
        stream: bool,
    ) -> Iterator[ChatChunk] | ChatResult:
        if stream:
            return self._stream(model=model, messages=messages, system_prompt=system_prompt, max_tokens=max_tokens, tier=tier)
        return self._once(model=model, messages=messages, system_prompt=system_prompt, max_tokens=max_tokens, tier=tier)

    def _build_kwargs(self, *, model: str, messages: list[dict], system_prompt: str, max_tokens: int, tier: Tier) -> dict:
        kwargs: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "system": [{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
            "messages": messages,
        }
        if tier == Tier.COMPLEX:
            kwargs["thinking"] = {"type": "adaptive"}
            kwargs["output_config"] = {"effort": "high"}
        elif tier == Tier.MEDIUM:
            kwargs["output_config"] = {"effort": "medium"}
        # Haiku (SIMPLE): no extra params — effort errors on Haiku 4.5
        return kwargs

    def _stream(self, **kwargs) -> Iterator[ChatChunk]:
        client = self._get_client()
        build_kw = self._build_kwargs(**kwargs)
        with client.messages.stream(**build_kw) as stream:
            for text in stream.text_stream:
                yield ChatChunk(token=text)

    def _once(self, **kwargs) -> ChatResult:
        client = self._get_client()
        build_kw = self._build_kwargs(**kwargs)
        # Non-streaming: remove stream kwarg if present, call create
        resp = client.messages.create(**build_kw)
        text = ""
        for block in resp.content:
            if hasattr(block, "text"):
                text += block.text
        return ChatResult(
            text=text,
            input_tokens=getattr(resp.usage, "input_tokens", 0),
            output_tokens=getattr(resp.usage, "output_tokens", 0),
            model=kwargs["model"],
            provider=self.name,
        )
