"""Tests for the persona_tone parameter in build_system_prompt."""
from __future__ import annotations

from jarvis.ai_clients import build_system_prompt

_CASUAL_ADDENDUM = "warmer, more conversational tone"


def test_formal_prompt_default_no_casual_addendum():
    prompt = build_system_prompt()
    assert _CASUAL_ADDENDUM not in prompt


def test_formal_explicit_no_casual_addendum():
    prompt = build_system_prompt(persona_tone="formal")
    assert _CASUAL_ADDENDUM not in prompt


def test_casual_prompt_contains_addendum():
    prompt = build_system_prompt(persona_tone="casual")
    assert _CASUAL_ADDENDUM in prompt


def test_unknown_tone_defaults_to_formal():
    prompt = build_system_prompt(persona_tone="pirate")
    assert _CASUAL_ADDENDUM not in prompt


def test_casual_addendum_does_not_break_base_prompt():
    prompt = build_system_prompt(persona_tone="casual")
    assert "J.A.R.V.I.S." in prompt
    assert "Never break character" in prompt


def test_formal_and_casual_differ():
    formal = build_system_prompt(persona_tone="formal")
    casual = build_system_prompt(persona_tone="casual")
    assert formal != casual
    assert len(casual) > len(formal)


def test_casual_with_user_name():
    prompt = build_system_prompt(user_name="Tony", persona_tone="casual")
    assert "Tony" in prompt
    assert _CASUAL_ADDENDUM in prompt


def test_casual_with_voice_mode():
    prompt = build_system_prompt(voice_mode=True, persona_tone="casual")
    assert "spoken aloud" in prompt
    assert _CASUAL_ADDENDUM in prompt
