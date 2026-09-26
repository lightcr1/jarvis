"""Tests fuer den zentralen Not-Aus."""
from __future__ import annotations

from jarvis import emergency
from jarvis.executor import Executor
from jarvis.zones import load_zones


def test_env_flag(tmp_path, monkeypatch):
    stop = tmp_path / "stop"
    monkeypatch.setenv("JARVIS_EMERGENCY_STOP_FILE", str(stop))
    monkeypatch.delenv("JARVIS_EMERGENCY_STOP", raising=False)
    assert emergency.is_active() is False
    monkeypatch.setenv("JARVIS_EMERGENCY_STOP", "1")
    assert emergency.is_active() is True


def test_file_flag_and_toggle(tmp_path, monkeypatch):
    stop = tmp_path / "nested" / "stop"
    monkeypatch.setenv("JARVIS_EMERGENCY_STOP_FILE", str(stop))
    monkeypatch.delenv("JARVIS_EMERGENCY_STOP", raising=False)
    assert emergency.is_active() is False
    assert emergency.set_active(True) is True and emergency.is_active() is True
    assert emergency.set_active(False) is True and emergency.is_active() is False


def test_executor_uses_central_flag(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_EMERGENCY_STOP_FILE", str(tmp_path / "stop"))
    monkeypatch.delenv("JARVIS_EMERGENCY_STOP", raising=False)
    monkeypatch.setattr("jarvis.emergency.is_active", lambda: True)
    executor = Executor(object(), zones=load_zones())
    assert executor.emergency_stop_active() is True
