from __future__ import annotations

import os
from typing import Iterator

from .base import BaseProvider, ChatChunk, ChatResult, ModelInfo
from .openai_compat import OpenAICompatibleProvider
from ..model_router import Tier


class _CompatShim(OpenAICompatibleProvider):
    """OpenAICompatibleProvider configured for the LOCAL_LLM_* env vars."""

    name = "local"
    supports_streaming = True

    def __init__(self, *, api_key: str | None = None, chat_fn=None, **kwargs):
        self.base_url = (os.getenv("LOCAL_LLM_BASE_URL") or "http://127.0.0.1:8000/v1").rstrip("/")
        super().__init__(api_key=api_key or os.getenv("LOCAL_LLM_API_KEY") or "", **kwargs)
        self._chat_fn = chat_fn


class LocalProvider(BaseProvider):
    """Local provider for the Runpod controller (or Ollama/other OpenAI-compatible).

    When LOCAL_LLM_BASE_URL and LOCAL_LLM_API_KEY are configured, requests are
    forwarded through the OpenAI-compatible client with streaming support. The
    legacy `local_ai_chat_reply` (non-streaming, deterministic) is used only as
    a fallback when no base URL/API key is configured.
    """

    name = "local"
    supports_streaming = True

    def __init__(self, *, api_key: str | None = None, chat_fn=None, **kwargs):
        self._api_key = api_key or os.getenv("LOCAL_LLM_API_KEY") or ""
        self._chat_fn = chat_fn

    @property
    def _compat(self) -> _CompatShim:
        return _CompatShim(api_key=self._api_key, chat_fn=self._chat_fn)

    def _get_chat_fn(self):
        if self._chat_fn is not None:
            return self._chat_fn
        from ..ai_clients import local_ai_chat_reply
        return local_ai_chat_reply

    def list_models(self) -> list[ModelInfo]:
        model_hint = (os.getenv("LOCAL_LLM_DEFAULT_MODEL") or "").strip()
        if model_hint:
            return [ModelInfo(model_hint, f"Local ({model_hint})", Tier.MEDIUM, 0.0, 0.0, supports_streaming=True)]
        return []

    def validate_api_key(self, api_key: str) -> tuple[bool, str]:
        return True, "n/a (local model)"

    def estimate_cost(self, *, model: str, input_tokens: int, output_tokens: int, price_table: dict | None = None) -> float:
        return 0.0

    def create_chat_completion(
        self,
        *,
        model: str,
        messages: list[dict],
        system_prompt: str,
        max_tokens: int,
        tier: Tier,
        stream: bool,
        tools: list[dict] | None = None,
    ) -> ChatResult | Iterator[ChatChunk]:
        base_url = os.getenv("LOCAL_LLM_BASE_URL") or ""
        api_key = self._api_key or os.getenv("LOCAL_LLM_API_KEY") or ""
        # Prefer the OpenAI-compatible endpoint (Runpod controller) when
        # configured — supports real streaming.
        if base_url:
            return self._compat.create_chat_completion(
                model=model,
                messages=messages,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                tier=tier,
                stream=stream,
                tools=tools,
            )
        # Legacy fallback: non-streaming deterministic helper.
        chat_fn = self._get_chat_fn()
        text = chat_fn(messages, system_prompt)
        chars = len(text)
        if stream:
            def _yield():
                if text:
                    yield ChatChunk(token=text)
            return _yield()
        return ChatResult(
            text=text,
            input_tokens=max(1, chars // 6),
            output_tokens=max(1, chars // 4),
            model=model,
            provider=self.name,
        )
