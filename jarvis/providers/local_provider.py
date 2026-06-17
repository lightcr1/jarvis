from __future__ import annotations

from typing import Iterator

from .base import BaseProvider, ChatChunk, ChatResult, ModelInfo
from ..model_router import Tier


class LocalProvider(BaseProvider):
    name = "local"
    supports_streaming = False

    def __init__(self, *, api_key: str | None = None, chat_fn=None, **kwargs):
        self._chat_fn = chat_fn

    def _get_chat_fn(self):
        if self._chat_fn is not None:
            return self._chat_fn
        from ..ai_clients import local_ai_chat_reply
        return local_ai_chat_reply

    def list_models(self) -> list[ModelInfo]:
        import os
        model_hint = (os.getenv("LOCAL_LLM_DEFAULT_MODEL") or "").strip()
        if model_hint:
            return [ModelInfo(model_hint, f"Local ({model_hint})", Tier.MEDIUM, 0.0, 0.0, supports_streaming=False)]
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
    ) -> ChatResult:
        chat_fn = self._get_chat_fn()
        text = chat_fn(messages, system_prompt)
        chars = len(text)
        return ChatResult(
            text=text,
            input_tokens=max(1, chars // 6),
            output_tokens=max(1, chars // 4),
            model=model,
            provider=self.name,
        )
