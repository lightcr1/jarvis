"""Base for OpenAI-compatible providers (OpenRouter, Mistral, DeepSeek)."""

from __future__ import annotations

import json
import os
from typing import Iterator

from .base import BaseProvider, ChatChunk, ChatResult, ModelInfo, ToolCall
from ..llm_utils import ReasoningStreamFilter, strip_reasoning_artifacts
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
        tools: list[dict] | None = None,
    ) -> Iterator[ChatChunk] | ChatResult:
        client = self._get_client()
        full_messages = [{"role": "system", "content": system_prompt}] + messages
        if stream:
            return self._stream(client, model, full_messages, max_tokens)
        return self._once(client, model, full_messages, max_tokens, tools)

    def _stream(self, client, model: str, messages: list[dict], max_tokens: int) -> Iterator[ChatChunk]:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            stream=True,
        )
        filt = ReasoningStreamFilter()
        for chunk in response:
            delta = (chunk.choices[0].delta.content or "") if chunk.choices else ""
            if delta:
                cleaned = filt.feed(delta)
                if cleaned:
                    yield ChatChunk(token=cleaned)
        tail = filt.flush()
        if tail:
            yield ChatChunk(token=tail)

    def _once(self, client, model: str, messages: list[dict], max_tokens: int, tools: list[dict] | None = None) -> ChatResult:
        kwargs: dict = {"model": model, "messages": messages, "max_tokens": max_tokens}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        resp = client.chat.completions.create(**kwargs)
        message = resp.choices[0].message if resp.choices else None
        text = strip_reasoning_artifacts((getattr(message, "content", None) or "").strip()) if message else ""
        tool_calls = [
            ToolCall(id=tc.id, name=tc.function.name, arguments=json.loads(tc.function.arguments or "{}"))
            for tc in (getattr(message, "tool_calls", None) or [])
        ]
        usage = resp.usage or type("U", (), {"prompt_tokens": 0, "completion_tokens": 0})()
        return ChatResult(
            text=text,
            input_tokens=getattr(usage, "prompt_tokens", 0),
            output_tokens=getattr(usage, "completion_tokens", 0),
            model=model,
            provider=self.name,
            tool_calls=tool_calls,
        )
