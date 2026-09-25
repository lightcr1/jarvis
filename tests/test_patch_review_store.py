"""Tests for the patch review queue (7.2)."""
from __future__ import annotations

import pytest

from jarvis.patch_review_store import PatchReviewStore


def _store(tmp_path):
    return PatchReviewStore(tmp_path / "patches.sqlite3")


def test_record_get_list_and_decide(tmp_path):
    store = _store(tmp_path)
    item = store.record(repository="owner/repo", branch="agent/x", base="dev",
                        commit="c1", message="Fix", patch="diff --git a/a b/a",
                        paths=["a.py"])
    assert item["status"] == "pending"
    assert item["paths"] == ["a.py"]
    assert [p["id"] for p in store.list()] == [item["id"]]
    decided = store.decide(item["id"], actor="owner", decision="pr_requested", pr_number=5)
    assert decided["status"] == "pr_requested" and decided["pr_number"] == 5
    # Nur einmal entscheidbar.
    assert store.decide(item["id"], actor="owner", decision="rejected") is None


def test_record_rejects_oversized_patch(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(ValueError, match="too large"):
        store.record(repository="owner/repo", branch="agent/x", base="dev", commit="c1",
                     message="Big", patch="x" * (1024 * 1024 + 1), paths=["a.py"])


def test_decide_rejects_unknown_decision(tmp_path):
    store = _store(tmp_path)
    item = store.record(repository="owner/repo", branch="agent/x", base="dev", commit="c1",
                        message="Fix", patch="p", paths=[])
    with pytest.raises(ValueError):
        store.decide(item["id"], actor="owner", decision="maybe")
