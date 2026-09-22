import json

from jarvis.autonomy_store import AutonomyStore


def test_missing_file_means_enabled(tmp_path):
    store = AutonomyStore(tmp_path / "autonomy.json")
    assert store.status()["enabled"] is True


def test_set_and_read_roundtrip(tmp_path):
    store = AutonomyStore(tmp_path / "autonomy.json")
    status = store.set_mode(False, actor="owner", note="pause for the night")
    assert status["enabled"] is False
    assert status["note"] == "pause for the night"
    assert store.status()["enabled"] is False
    assert json.loads((tmp_path / "autonomy.json").read_text())["updated_by"] == "owner"


def test_rewrite_keeps_latest_values(tmp_path):
    store = AutonomyStore(tmp_path / "autonomy.json")
    store.set_mode(True, actor="owner", note="first")
    store.set_mode(False, actor="owner", note="second")
    data = json.loads((tmp_path / "autonomy.json").read_text())
    assert data["note"] == "second"
