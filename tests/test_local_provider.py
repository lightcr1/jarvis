import os

from jarvis.providers.local_provider import LocalProvider
from jarvis.model_router import Tier


def test_local_provider_streams_via_openai_compat(monkeypatch):
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", "http://controller:8080/chat/v1")
    monkeypatch.setenv("LOCAL_LLM_API_KEY", "sekret-key" * 5)
    p = LocalProvider()
    assert p.supports_streaming is True
    compat = p._compat
    assert compat.base_url == "http://controller:8080/chat/v1"


def test_local_provider_fallback_without_base_url(monkeypatch):
    monkeypatch.delenv("LOCAL_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LOCAL_LLM_API_KEY", raising=False)
    p = LocalProvider()
    result = p.create_chat_completion(
        model="chat", messages=[{"role": "user", "content": "hi"}],
        system_prompt="be nice", max_tokens=64, tier=Tier.SIMPLE, stream=False,
    )
    assert result.text is not None
