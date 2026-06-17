"""Base for OpenAI-compatible providers (OpenRouter, Mistral, DeepSeek)."""

from __future__ import annotations

import os
from typing import Iterator

from .base import BaseProvider, ChatChunk, ChatResult, ModelInfo
from ..model_router import Tier


class OpenAICompatibleProvider(BaseProvider):
    """Shared implementation for any OpenAI-compatible API endpoint."""

    name = "openai_compat"
    supports_streaming = True
    base_url: str = ""
    _env_key_var: str = ""

    def __init__(self, *, api_key: str | None = None, client_factory=None, **kwargs):
        self._api_key = api_key or os.getenv(self._env_key_var) or ""
        self._client_factory = client_factory

    def _get_client(self):
        if self._client_factory is not None:
            return self._client_factory()
        from openai import OpenAI
        return OpenAI(api_key=self._api_key, base_url=self.base_url, timeout=30.0, max_retries=1)

    def validate_api_key(self, api_key: str) -> tuple[bool, str]:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key, base_url=self.base_url, timeout=10.0, max_retries=0)
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
