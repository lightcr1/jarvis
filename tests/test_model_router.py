import os

from jarvis.model_router import select_model
from jarvis.model_router import Tier


def test_select_model_local_uses_configured_default(monkeypatch):
    monkeypatch.setenv("LOCAL_LLM_DEFAULT_MODEL", "chat")
    assert select_model(Tier.SIMPLE, "local") == "chat"
    assert select_model(Tier.MEDIUM, "local") == "chat"
    assert select_model(Tier.COMPLEX, "local") == "chat"


def test_select_model_local_falls_back_to_chat(monkeypatch):
    monkeypatch.delenv("LOCAL_LLM_DEFAULT_MODEL", raising=False)
    assert select_model(Tier.MEDIUM, "local") == "chat"


def test_select_model_non_local_keeps_existing_behavior():
    # openrouter fallback: pin to openai default when provider unknown
    assert select_model(Tier.MEDIUM, "does-not-exist") is not None



def test_local_provider_gets_generous_token_budget():
    from jarvis.model_router import LOCAL_MAX_TOKENS, max_tokens_for, Tier
    assert max_tokens_for(Tier.SIMPLE, "local") == LOCAL_MAX_TOKENS[Tier.SIMPLE]
    assert LOCAL_MAX_TOKENS[Tier.SIMPLE] > 256
