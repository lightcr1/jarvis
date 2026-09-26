"""Tests fuer Pod-Start-Client und Monatsbudget (Review-Punkt 2a)."""
from __future__ import annotations

import pytest

from jarvis.pod_control import PodControl, PodError, estimate_cost_chf, within_budget


def test_budget_math(tmp_path, monkeypatch):
    assert estimate_cost_chf(0.5, 4) == 2.0
    monkeypatch.setenv("JARVIS_POD_MONTHLY_BUDGET_CHF", "20")
    assert within_budget(2.0, 10.0) is True
    assert within_budget(15.0, 10.0) is False
    monkeypatch.setenv("JARVIS_POD_MONTHLY_BUDGET_CHF", "0")
    assert within_budget(1.0, 0.0) is False          # ohne gesetztes Budget kein Start


def test_from_env_none_without_config():
    assert PodControl.from_env({}) is None
    assert PodControl.from_env({"JARVIS_CONTROLLER_URL": "https://c"}) is None
    client = PodControl.from_env({"JARVIS_CONTROLLER_URL": "https://c/", "CONTROL_TOKEN": "t"})
    assert client is not None and client.base_url == "https://c" and client.control_token == "t"


def test_start_and_errors():
    calls = []
    def transport(method, path, body=None):
        calls.append((method, path, body))
        return (200, {"status": "starting"}) if path == "/api/pod/start" else (500, {})
    client = PodControl("https://c", "t", transport=transport)
    assert client.start("default")["status"] == "starting"
    assert calls == [("POST", "/api/pod/start", {"profile": "default"})]
    with pytest.raises(PodError):
        client.stop()
