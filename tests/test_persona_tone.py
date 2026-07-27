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


def test_no_context_mode_by_default():
    prompt = build_system_prompt()
    assert "QUIET HOURS ACTIVE" not in prompt
    assert "LATE HOUR" not in prompt
    assert "MORNING CONTEXT" not in prompt


def test_quiet_hours_active_overrides_time_of_day():
    prompt = build_system_prompt(time_of_day="morning", quiet_hours_active=True)
    assert "QUIET HOURS ACTIVE" in prompt
    assert "MORNING CONTEXT" not in prompt


def test_night_time_of_day_line():
    prompt = build_system_prompt(time_of_day="night")
    assert "LATE HOUR" in prompt


def test_morning_time_of_day_line():
    prompt = build_system_prompt(time_of_day="morning")
    assert "MORNING CONTEXT" in prompt


def test_day_and_evening_add_no_context_line():
    for tod in ("day", "evening"):
        prompt = build_system_prompt(time_of_day=tod)
        assert "QUIET HOURS ACTIVE" not in prompt
        assert "LATE HOUR" not in prompt
        assert "MORNING CONTEXT" not in prompt


def test_no_related_history_by_default():
    prompt = build_system_prompt()
    assert "RELEVANT PAST CONVERSATIONS" not in prompt


def test_related_history_included():
    prompt = build_system_prompt(related_history=['On Jan 05 you discussed: "the API migration"'])
    assert "RELEVANT PAST CONVERSATIONS" in prompt
    assert "API migration" in prompt


def test_related_history_capped_at_three():
    prompt = build_system_prompt(related_history=["one", "two", "three", "four"])
    assert "one" in prompt and "two" in prompt and "three" in prompt
    assert "four" not in prompt
