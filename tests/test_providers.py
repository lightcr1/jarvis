"""Tests for the provider abstraction layer (Phase 1). No real network calls."""
import pytest
from unittest.mock import MagicMock
from jarvis.model_router import Tier
from jarvis.providers.base import ChatChunk, ChatResult, ModelInfo
from jarvis.providers import get_provider_instance


# ─── Cost estimation ──────────────────────────────────────────────────────────

def test_base_estimate_cost_zero_without_table():
    from jarvis.providers.openai_provider import OpenAIProvider
    p = OpenAIProvider(api_key="x")
    cost = p.estimate_cost(model="gpt-4o", input_tokens=1000, output_tokens=500)
    assert cost == 0.0


def test_base_estimate_cost_with_table():
    from jarvis.providers.openai_provider import OpenAIProvider
    p = OpenAIProvider(api_key="x")
    table = {"gpt-4o": {"in": 2.5, "out": 10.0}}
    cost = p.estimate_cost(model="gpt-4o", input_tokens=1_000_000, output_tokens=1_000_000, price_table=table)
    assert abs(cost - 12.5) < 0.001


def test_base_estimate_cost_unknown_model_zero():
    from jarvis.providers.openai_provider import OpenAIProvider
    p = OpenAIProvider(api_key="x")
    table = {"gpt-4o": {"in": 2.5, "out": 10.0}}
    cost = p.estimate_cost(model="unknown-model", input_tokens=1_000_000, output_tokens=500_000, price_table=table)
    assert cost == 0.0


def test_local_estimate_cost_always_zero():
    from jarvis.providers.local_provider import LocalProvider
    p = LocalProvider(chat_fn=lambda msgs, sp: "reply")
    table = {"local-model": {"in": 99.0, "out": 99.0}}
    cost = p.estimate_cost(model="local-model", input_tokens=99999, output_tokens=99999, price_table=table)
    assert cost == 0.0


# ─── Registry ─────────────────────────────────────────────────────────────────

def test_get_provider_instance_known_providers():
    for name in ["anthropic", "openai", "gemini", "local", "openrouter", "mistral", "deepseek"]:
        p = get_provider_instance(name, api_key="x")
        assert p.name == name


def test_get_provider_instance_unknown_raises():
    with pytest.raises(ValueError, match="Unknown provider"):
        get_provider_instance("doesnotexist")


# ─── List models (static fallbacks, no network) ───────────────────────────────

def test_anthropic_list_models():
    from jarvis.providers.anthropic_provider import AnthropicProvider
    p = AnthropicProvider(api_key="x")
    models = p.list_models()
    ids = [m.id for m in models]
    assert "claude-haiku-4-5" in ids
    assert "claude-opus-4-8" in ids


def test_openrouter_list_models():
    from jarvis.providers.openrouter_provider import OpenRouterProvider
    p = OpenRouterProvider(api_key="x")
    models = p.list_models()
    assert len(models) > 0
    assert any("claude" in m.id for m in models)


def test_local_list_models_empty_without_env(monkeypatch):
    monkeypatch.delenv("LOCAL_LLM_DEFAULT_MODEL", raising=False)
    from jarvis.providers.local_provider import LocalProvider
    p = LocalProvider()
    assert p.list_models() == []


# ─── Streaming yields ChatChunk ───────────────────────────────────────────────

def test_openai_streaming_yields_chunks():
    from jarvis.providers.openai_provider import OpenAIProvider

    mock_client = MagicMock()
    chunk1 = MagicMock(); chunk1.choices = [MagicMock(delta=MagicMock(content="Hello"))]
    chunk2 = MagicMock(); chunk2.choices = [MagicMock(delta=MagicMock(content=" world"))]
    mock_client.chat.completions.create.return_value = iter([chunk1, chunk2])

    p = OpenAIProvider(client_factory=lambda: mock_client)
    result = p.create_chat_completion(
        model="gpt-4o-mini", messages=[{"role": "user", "content": "hi"}],
        system_prompt="sys", max_tokens=100, tier=Tier.SIMPLE, stream=True,
    )
    chunks = list(result)
    assert chunks == [ChatChunk("Hello"), ChatChunk(" world")]


def test_openai_non_streaming_returns_chat_result():
    from jarvis.providers.openai_provider import OpenAIProvider

    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(message=MagicMock(content="Answer"))]
    mock_resp.usage = MagicMock(prompt_tokens=10, completion_tokens=5)
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_resp

    p = OpenAIProvider(client_factory=lambda: mock_client)
    result = p.create_chat_completion(
        model="gpt-4o", messages=[{"role": "user", "content": "?"}],
        system_prompt="sys", max_tokens=200, tier=Tier.MEDIUM, stream=False,
    )
    assert isinstance(result, ChatResult)
    assert result.text == "Answer"
    assert result.input_tokens == 10
    assert result.output_tokens == 5
    assert result.provider == "openai"


def test_local_returns_chat_result():
    from jarvis.providers.local_provider import LocalProvider

    chat_fn = lambda msgs, sp: "Local reply"
    p = LocalProvider(chat_fn=chat_fn)
    result = p.create_chat_completion(
        model="local-model", messages=[{"role": "user", "content": "hi"}],
        system_prompt="sys", max_tokens=128, tier=Tier.SIMPLE, stream=False,
    )
    assert isinstance(result, ChatResult)
    assert result.text == "Local reply"
    assert result.provider == "local"


def test_openrouter_streaming_yields_chunks():
    from jarvis.providers.openrouter_provider import OpenRouterProvider

    mock_client = MagicMock()
    chunk = MagicMock(); chunk.choices = [MagicMock(delta=MagicMock(content="OR response"))]
    mock_client.chat.completions.create.return_value = iter([chunk])

    p = OpenRouterProvider(client_factory=lambda: mock_client)
    result = p.create_chat_completion(
        model="anthropic/claude-haiku-4-5", messages=[{"role": "user", "content": "test"}],
        system_prompt="sys", max_tokens=256, tier=Tier.SIMPLE, stream=True,
    )
    chunks = list(result)
    assert chunks == [ChatChunk("OR response")]


def test_openrouter_streaming_strips_think_block_split_across_chunks():
    from jarvis.providers.openrouter_provider import OpenRouterProvider

    pieces = ["Before ", "<thi", "nk>reasoning here</th", "ink> After"]
    chunks_in = []
    for piece in pieces:
        c = MagicMock()
        c.choices = [MagicMock(delta=MagicMock(content=piece))]
        chunks_in.append(c)
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = iter(chunks_in)

    p = OpenRouterProvider(client_factory=lambda: mock_client)
    result = p.create_chat_completion(
        model="anthropic/claude-haiku-4-5", messages=[{"role": "user", "content": "test"}],
        system_prompt="sys", max_tokens=256, tier=Tier.SIMPLE, stream=True,
    )
    text = "".join(c.token for c in result)
    assert text == "Before  After"
    assert "reasoning here" not in text


def test_openrouter_non_streaming_strips_reasoning_and_safety_preamble():
    from jarvis.providers.openrouter_provider import OpenRouterProvider

    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(message=MagicMock(
        content="User Safety: safe\nResponse Safety: safe\n\n<think>internal notes</think>Actual reply.",
        tool_calls=None,
    ))]
    mock_resp.usage = MagicMock(prompt_tokens=10, completion_tokens=5)
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_resp

    p = OpenRouterProvider(client_factory=lambda: mock_client)
    result = p.create_chat_completion(
        model="anthropic/claude-haiku-4-5", messages=[{"role": "user", "content": "?"}],
        system_prompt="sys", max_tokens=200, tier=Tier.MEDIUM, stream=False,
    )
    assert result.text == "Actual reply."


def test_openrouter_non_streaming_passes_tools_and_parses_tool_calls():
    from jarvis.providers.openrouter_provider import OpenRouterProvider

    tool_call = MagicMock()
    tool_call.id = "call_1"
    tool_call.function.name = "get_proxmox_status"
    tool_call.function.arguments = '{"host_id": "h1"}'
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(message=MagicMock(content=None, tool_calls=[tool_call]))]
    mock_resp.usage = MagicMock(prompt_tokens=10, completion_tokens=5)
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_resp

    p = OpenRouterProvider(client_factory=lambda: mock_client)
    tools_schema = [{"type": "function", "function": {"name": "get_proxmox_status", "description": "d", "parameters": {}}}]
    result = p.create_chat_completion(
        model="anthropic/claude-haiku-4-5", messages=[{"role": "user", "content": "status?"}],
        system_prompt="sys", max_tokens=200, tier=Tier.MEDIUM, stream=False, tools=tools_schema,
    )
    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["tools"] == tools_schema
    assert call_kwargs["tool_choice"] == "auto"
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "get_proxmox_status"
    assert result.tool_calls[0].arguments == {"host_id": "h1"}


# ─── Validate API key (monkeypatched, no network) ─────────────────────────────

def test_validate_key_skipped_for_local():
    from jarvis.providers.local_provider import LocalProvider
    p = LocalProvider()
    ok, detail = p.validate_api_key("anything")
    assert ok is True


def test_validate_key_openai_ok(monkeypatch):
    from jarvis.providers.openai_provider import OpenAIProvider
    import openai

    mock_client = MagicMock()
    mock_client.models.list.return_value = []
    monkeypatch.setattr(openai, "OpenAI", lambda **kw: mock_client)

    p = OpenAIProvider(api_key="sk-test")
    ok, detail = p.validate_api_key("sk-test")
    assert ok is True


def test_validate_key_openai_fail(monkeypatch):
    from jarvis.providers.openai_provider import OpenAIProvider
    import openai

    def bad_client(**kw):
        raise openai.AuthenticationError("bad key", response=MagicMock(status_code=401), body={})

    monkeypatch.setattr(openai, "OpenAI", bad_client)

    p = OpenAIProvider(api_key="sk-bad")
    ok, detail = p.validate_api_key("sk-bad")
    assert ok is False


# ─── model_router PROVIDER_ORDER ─────────────────────────────────────────────

def test_provider_order_contains_all():
    from jarvis.model_router import PROVIDER_ORDER
    for name in ["openrouter", "anthropic", "openai", "gemini", "mistral", "deepseek", "local"]:
        assert name in PROVIDER_ORDER
    assert PROVIDER_ORDER[-1] == "local"


def test_models_dict_has_new_providers():
    from jarvis.model_router import MODELS, Tier
    assert "openrouter" in MODELS
    assert "mistral" in MODELS
    assert "deepseek" in MODELS
    # Must route to real, specific models — not a placeholder "free" slug that
    # silently lands on whatever unreliable/low-quality model OpenRouter picks.
    for tier in (Tier.SIMPLE, Tier.MEDIUM, Tier.COMPLEX):
        assert MODELS["openrouter"][tier] != "openrouter/free"
        assert "/" in MODELS["openrouter"][tier]


# ─── Gemini provider — tool-calling ───────────────────────────────────────────

def test_gemini_text_only_completion():
    from jarvis.providers.gemini_provider import GeminiProvider

    mock_resp = MagicMock()
    mock_resp.text = "Hello there."
    mock_resp.function_calls = None
    mock_resp.usage_metadata = MagicMock(prompt_token_count=10, candidates_token_count=4)
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_resp

    p = GeminiProvider(client_factory=lambda: mock_client)
    result = p.create_chat_completion(
        model="gemini-2.5-flash", messages=[{"role": "user", "content": "hi"}],
        system_prompt="sys", max_tokens=200, tier=Tier.MEDIUM, stream=False,
    )
    assert result.text == "Hello there."
    assert result.tool_calls == []


def test_gemini_passes_function_declarations_when_tools_given():
    from jarvis.providers.gemini_provider import GeminiProvider

    mock_resp = MagicMock()
    mock_resp.text = ""
    mock_resp.function_calls = None
    mock_resp.usage_metadata = None
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_resp

    p = GeminiProvider(client_factory=lambda: mock_client)
    tools_schema = [{
        "type": "function",
        "function": {"name": "get_login_history", "description": "d", "parameters": {"type": "object", "properties": {}}},
    }]
    p.create_chat_completion(
        model="gemini-2.5-flash", messages=[{"role": "user", "content": "who logged in?"}],
        system_prompt="sys", max_tokens=200, tier=Tier.MEDIUM, stream=False, tools=tools_schema,
    )
    call_kwargs = mock_client.models.generate_content.call_args.kwargs
    config = call_kwargs["config"]
    assert len(config.tools) == 1
    assert config.tools[0].function_declarations[0].name == "get_login_history"


def test_gemini_parses_function_call_response():
    from google.genai import types
    from jarvis.providers.gemini_provider import GeminiProvider

    fc = types.FunctionCall(name="proxmox_status", args={})
    mock_resp = MagicMock()
    mock_resp.text = ""
    mock_resp.function_calls = [fc]
    mock_resp.usage_metadata = None
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_resp

    p = GeminiProvider(client_factory=lambda: mock_client)
    result = p.create_chat_completion(
        model="gemini-2.5-flash", messages=[{"role": "user", "content": "proxmox status?"}],
        system_prompt="sys", max_tokens=200, tier=Tier.MEDIUM, stream=False,
        tools=[{
            "type": "function",
            "function": {"name": "proxmox_status", "description": "d", "parameters": {"type": "object", "properties": {}}},
        }],
    )
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "proxmox_status"
    assert result.tool_calls[0].arguments == {}
    assert result.tool_calls[0].id  # synthesized fallback id since FunctionCall.id is None here


def test_gemini_no_text_no_tools_falls_back_to_placeholder():
    from jarvis.providers.gemini_provider import GeminiProvider

    mock_resp = MagicMock()
    mock_resp.text = ""
    mock_resp.function_calls = None
    mock_resp.usage_metadata = None
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_resp

    p = GeminiProvider(client_factory=lambda: mock_client)
    result = p.create_chat_completion(
        model="gemini-2.5-flash", messages=[{"role": "user", "content": "hi"}],
        system_prompt="sys", max_tokens=200, tier=Tier.MEDIUM, stream=False,
    )
    assert "No output" in result.text


def test_gemini_translates_openai_style_tool_exchange_into_function_parts():
    from jarvis.providers.gemini_provider import _to_gemini_messages

    messages = [
        {"role": "user", "content": "what's the proxmox status?"},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "call_1", "type": "function", "function": {"name": "proxmox_status", "arguments": "{}"}},
        ]},
        {"role": "tool", "tool_call_id": "call_1", "content": '{"configured": true, "summary": {"running": 4}}'},
    ]
    contents = _to_gemini_messages(messages)
    assert len(contents) == 3
    assert contents[0].role == "user"
    assert contents[1].role == "model"
    assert contents[1].parts[0].function_call.name == "proxmox_status"
    assert contents[2].role == "user"
    assert contents[2].parts[0].function_response.name == "proxmox_status"
    assert contents[2].parts[0].function_response.response == {"configured": True, "summary": {"running": 4}}
