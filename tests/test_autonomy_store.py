import json

import pytest

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


def test_policy_roundtrip_and_validation(tmp_path):
    store = AutonomyStore(tmp_path / "autonomy.json")
    status = store.set_policy(actor="owner", max_gpu_hours_per_day=6,
                              allowed_windows=["22:00-06:00"],
                              max_rounds_per_pod_session=10)
    assert status["max_gpu_hours_per_day"] == 6
    assert status["allowed_windows"] == ["22:00-06:00"]
    assert status["max_rounds_per_pod_session"] == 10
    assert store.policy()["max_rounds_per_pod_session"] == 10
    with pytest.raises(ValueError):
        store.set_policy(actor="owner", allowed_windows=["not-a-window"])
    # set_mode erhaelt die Policy-Felder.
    store.set_mode(True, actor="owner")
    assert store.policy()["max_gpu_hours_per_day"] == 6
