from jarvis.model_router import Tier, classify_complexity, select_model, max_tokens_for, should_use_extended_thinking


def test_simple_voice_short():
    assert classify_complexity("turn on the lights", voice_mode=True) == Tier.SIMPLE


def test_simple_short_no_signals():
    assert classify_complexity("what time is it") == Tier.SIMPLE


def test_medium_question():
    assert classify_complexity("what is the difference between LXC and VMs") == Tier.MEDIUM


def test_complex_long_text():
    long = "explain " + "word " * 160
    assert classify_complexity(long) == Tier.COMPLEX


def test_complex_keyword_hits():
    assert classify_complexity("implement a secure authentication architecture with step by step database design") == Tier.COMPLEX


def test_deep_history_boosts_tier():
    assert classify_complexity("ok", history_len=12) == Tier.MEDIUM


def test_select_model_anthropic():
    assert select_model(Tier.SIMPLE, "anthropic") == "claude-haiku-4-5"
    assert select_model(Tier.MEDIUM, "anthropic") == "claude-sonnet-4-6"
    assert select_model(Tier.COMPLEX, "anthropic") == "claude-opus-4-8"


def test_select_model_openai():
    assert select_model(Tier.SIMPLE, "openai") == "gpt-4o-mini"
    assert select_model(Tier.COMPLEX, "openai") == "gpt-4o"


def test_max_tokens():
    assert max_tokens_for(Tier.SIMPLE) == 256
    assert max_tokens_for(Tier.MEDIUM) == 1024
    assert max_tokens_for(Tier.COMPLEX) == 4096


def test_extended_thinking_only_opus_complex():
    assert should_use_extended_thinking(Tier.COMPLEX, "anthropic") is True
    assert should_use_extended_thinking(Tier.MEDIUM, "anthropic") is False
    assert should_use_extended_thinking(Tier.SIMPLE, "anthropic") is False
    assert should_use_extended_thinking(Tier.COMPLEX, "openai") is False


def test_voice_mode_caps_at_simple():
    # Long voice commands still become simple if word count <= 15
    assert classify_complexity("set the thermostat to twenty degrees", voice_mode=True) == Tier.SIMPLE


def test_voice_mode_longer_goes_through_scoring():
    # Voice + 16+ words falls through normal scoring (threshold is <= 15)
    result = classify_complexity(
        "can you explain how the proxmox cluster architecture works and compare it to a docker swarm setup please",
        voice_mode=True,
    )
    assert result in (Tier.MEDIUM, Tier.COMPLEX)
