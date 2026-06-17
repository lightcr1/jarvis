from __future__ import annotations

import os
from typing import Iterator

from .base import BaseProvider, ChatChunk, ChatResult, ModelInfo
from ..model_router import Tier

_MODELS = [
    ModelInfo("gemini-2.0-flash", "Gemini 2.0 Flash", Tier.SIMPLE, 0.1, 0.4),
    ModelInfo("gemini-2.5-flash", "Gemini 2.5 Flash", Tier.MEDIUM, 0.3, 2.5),
    ModelInfo("gemini-1.5-pro", "Gemini 1.5 Pro", Tier.COMPLEX, 1.25, 5.0),
]


class GeminiProvider(BaseProvider):
    name = "gemini"
    supports_streaming = False  # current integration is non-streaming (single done event)

    def __init__(self, *, api_key: str | None = None, client_factory=None):
        self._api_key = api_key or os.getenv("GEMINI_API_KEY") or ""
        self._client_factory = client_factory

    def _get_client(self):
        if self._client_factory is not None:
            return self._client_factory()
        from google import genai
        return genai.Client(api_key=self._api_key)

    def list_models(self) -> list[ModelInfo]:
        return list(_MODELS)

    def validate_api_key(self, api_key: str) -> tuple[bool, str]:
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            list(client.models.list())
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
        from google.genai import types as _gtypes
        client = self._get_client()
        gemini_messages = [
            _gtypes.Content(
                role="user" if m["role"] == "user" else "model",
                parts=[_gtypes.Part(text=m.get("content", ""))],
            )
            for m in messages
        ]
        config = _gtypes.GenerateContentConfig(
            system_instruction=system_prompt if system_prompt else None,
            max_output_tokens=max_tokens,
        )
        resp = client.models.generate_content(
            model=model,
            contents=gemini_messages,
            config=config,
        )
        text = (getattr(resp, "text", "") or "").strip() or "On it. (No output returned.)"
        usage = getattr(resp, "usage_metadata", None)
        in_tok = getattr(usage, "prompt_token_count", None) or max(1, len(str(messages)) // 4)
        out_tok = getattr(usage, "candidates_token_count", None) or max(1, len(text) // 4)
        return ChatResult(
            text=text,
            input_tokens=in_tok,
            output_tokens=out_tok,
            model=model,
            provider=self.name,
        )
