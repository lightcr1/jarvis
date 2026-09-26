"""Datenklassen (2.4): public/personal/sensitive und Cloud-Gating."""
from __future__ import annotations

from pathlib import Path

from jarvis.data_classes import (
    PERSONAL, PUBLIC, SENSITIVE, allowed_for_cloud, filter_for_provider, is_cloud_provider, normalize,
)
from jarvis.memory_store import MemoryStore


def test_normalize_defaults_to_personal():
    assert normalize(PUBLIC) == PUBLIC
    assert normalize(" SENSITIVE ") == SENSITIVE
    assert normalize("nonsense") == PERSONAL
    assert normalize(None) == PERSONAL


def test_cloud_allowed_only_public_and_consented_personal():
    assert allowed_for_cloud(PUBLIC) is True
    assert allowed_for_cloud(PERSONAL) is False
    assert allowed_for_cloud(PERSONAL, consent=True) is True
    assert allowed_for_cloud(SENSITIVE, consent=True) is False


def test_local_provider_is_never_cloud():
    assert is_cloud_provider("local") is False
    assert is_cloud_provider("openai") is True
    assert is_cloud_provider(None) is True


def test_filter_for_provider():
    notes = [{"text": "a", "data_class": PUBLIC},
             {"text": "b", "data_class": PERSONAL},
             {"text": "c", "data_class": SENSITIVE}]
    assert [n["text"] for n in filter_for_provider(notes, "local")] == ["a", "b", "c"]
    assert [n["text"] for n in filter_for_provider(notes, "openai")] == ["a"]
    assert [n["text"] for n in filter_for_provider(notes, "openai", consent=True)] == ["a", "b"]
    assert [n["text"] for n in filter_for_provider(notes, "gemini", consent=True)] == ["a", "b"]


def test_memory_notes_carry_and_update_data_class(tmp_path):
    store = MemoryStore(tmp_path / "memory.json")
    note = store.add_note("u", "public fact", PUBLIC)
    assert note["data_class"] == PUBLIC
    assert store.add_note("u", "secret")["data_class"] == PERSONAL
    updated = store.set_note_class("u", note["id"], SENSITIVE)
    assert updated["data_class"] == SENSITIVE
    assert store.set_note_class("u", "missing", PUBLIC) is None
    assert [n["data_class"] for n in store.get_notes("u")] == [SENSITIVE, PERSONAL]


def test_legacy_notes_default_to_personal(tmp_path):
    path = Path(tmp_path / "memory.json")
    path.write_text('{"schema_version": 1, "users": {"u": {"notes": [{"id": "x", "text": "old", "created_at": 1}], "aliases": {}}}}')
    store = MemoryStore(path)
    assert store.get_notes("u")[0]["data_class"] == PERSONAL
