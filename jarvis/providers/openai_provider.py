from __future__ import annotations

import os
from typing import Iterator

from .base import BaseProvider, ChatChunk, ChatResult, ModelInfo
from ..model_router import Tier

_MODELS = [
    ModelInfo("gpt-4o-mini", "GPT-4o Mini", Tier.SIMPLE, 0.15, 0.6),
    ModelInfo("gpt-4o", "GPT-4o", Tier.MEDIUM, 2.5, 10.0),
    ModelInfo("gpt-4.1-mini", "GPT-4.1 Mini", Tier.SIMPLE, 0.4, 1.6),
    ModelInfo("gpt-4.1", "GPT-4.1", Tier.MEDIUM, 2.0, 8.0),
]


class OpenAIProvider(BaseProvider):
    name = "openai"
    supports_streaming = True

    def __init__(self, *, api_key: str | None = None, client_factory=None):
        self._api_key = api_key or os.getenv("OPENAI_API_KEY") or ""
        self._client_factory = client_factory

    def _get_client(self):
        if self._client_factory is not None:
            return self._client_factory()
        from openai import OpenAI
        return OpenAI(api_key=self._api_key, timeout=20.0, max_retries=1)

    def list_models(self) -> list[ModelInfo]:
        return list(_MODELS)

    def validate_api_key(self, api_key: str) -> tuple[bool, str]:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key, timeout=10.0, max_retries=0)
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
        client = self._get_client()
        full_messages = [{"role": "system", "content": system_prompt}] + messages
        if stream:
            return self._stream(client, model, full_messages, max_tokens)
        return self._once(client, model, full_messages, max_tokens)

    def _stream(self, client, model: str, messages: list[dict], max_tokens: int) -> Iterator[ChatChunk]:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.3,
            max_tokens=max_tokens,
            stream=True,
        )
        for chunk in response:
            delta = (chunk.choices[0].delta.content or "") if chunk.choices else ""
            if delta:
                yield ChatChunk(token=delta)

    def _once(self, client, model: str, messages: list[dict], max_tokens: int) -> ChatResult:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.3,
            max_tokens=max_tokens,
        )
        text = (resp.choices[0].message.content or "").strip() if resp.choices else ""
        usage = resp.usage or type("U", (), {"prompt_tokens": 0, "completion_tokens": 0})()
        return ChatResult(
            text=text,
            input_tokens=getattr(usage, "prompt_tokens", 0),
            output_tokens=getattr(usage, "completion_tokens", 0),
            model=model,
            provider=self.name,
        )
