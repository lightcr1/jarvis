"""Tests for the language parameter in build_system_prompt (German localization)."""
from __future__ import annotations

from jarvis.ai_clients import build_system_prompt


def test_defaults_to_english():
    prompt = build_system_prompt()
    assert "You are J.A.R.V.I.S." in prompt
    assert "TONE:" in prompt


def test_german_persona_is_localized_not_appended():
    prompt = build_system_prompt(language="de")
    assert "Du bist J.A.R.V.I.S." in prompt
    assert "TONVERHALTEN:" in prompt
    assert "You are J.A.R.V.I.S." not in prompt
    assert "TONE:" not in prompt


def test_unknown_language_falls_back_to_english():
    prompt = build_system_prompt(language="fr")
    assert "You are J.A.R.V.I.S." in prompt


def test_german_user_name_addressed_in_german():
    prompt = build_system_prompt(user_name="Lukas", language="de")
    assert "Sprich den Benutzer als 'Lukas' an." in prompt


def test_german_location_and_notes_localized():
    prompt = build_system_prompt(location="Aarau", notes=["Meeting um 10"], language="de")
    assert "PERSÖNLICHER KONTEXT:" in prompt
    assert "Standort des Benutzers: Aarau." in prompt
    assert "Persönliche Notizen des Benutzers: Meeting um 10." in prompt


def test_german_voice_mode_instruction():
    prompt = build_system_prompt(voice_mode=True, language="de")
    assert "SPRACHMODUS:" in prompt
    assert "KEINE Markdown-Formatierung" in prompt


def test_german_casual_tone_addendum():
    prompt = build_system_prompt(persona_tone="casual", language="de")
    assert "TONANPASSUNG:" in prompt


def test_german_quiet_hours_and_time_of_day():
    quiet = build_system_prompt(quiet_hours_active=True, language="de")
    assert "RUHEZEIT AKTIV:" in quiet

    night = build_system_prompt(time_of_day="night", language="de")
    assert "SPÄTE STUNDE:" in night

    morning = build_system_prompt(time_of_day="morning", language="de")
    assert "MORGENKONTEXT:" in morning


def test_german_related_history_localized():
    prompt = build_system_prompt(related_history=["discussed the migration"], language="de")
    assert "RELEVANTE VERGANGENE GESPRÄCHE:" in prompt
