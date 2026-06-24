"""Tests for _parse_duration and the timer/reminder skill routing."""
from __future__ import annotations

import pytest

from jarvis.assistant_domain import _parse_duration


# ── _parse_duration unit tests ────────────────────────────────────────────────

def test_en_minutes_basic():
    result = _parse_duration("set a timer for 20 minutes")
    assert result == (1200, "")


def test_en_minutes_short_keyword():
    result = _parse_duration("timer for 10 min")
    assert result == (600, "")


def test_en_hours():
    result = _parse_duration("timer 2 hours")
    assert result == (7200, "")


def test_en_seconds():
    result = _parse_duration("remind me in 45 seconds to check the server")
    assert result is not None
    secs, label = result
    assert secs == 45
    assert "check the server" in label


def test_en_compound_1h30m():
    result = _parse_duration("timer 1h30m")
    assert result == (5400, "")


def test_en_compound_with_spaces():
    result = _parse_duration("set a timer for 1 hour 30 minutes")
    assert result is not None
    assert result[0] == 5400


def test_en_with_label():
    result = _parse_duration("remind me in 20 minutes to check the server")
    assert result is not None
    secs, label = result
    assert secs == 1200
    assert label == "check the server"


def test_en_in_prefix():
    result = _parse_duration("in 30 minutes")
    assert result == (1800, "")


def test_de_minutes():
    result = _parse_duration("stell einen timer auf 10 minuten")
    assert result is not None
    assert result[0] == 600


def test_de_hours():
    result = _parse_duration("erinnere mich in 2 stunden")
    assert result is not None
    assert result[0] == 7200


def test_de_timer_fuer():
    result = _parse_duration("timer für 5 minuten")
    assert result is not None
    assert result[0] == 300


def test_de_in_prefix():
    result = _parse_duration("in 30 minuten")
    assert result == (1800, "")


def test_invalid_input_returns_none():
    assert _parse_duration("hello world") is None
    assert _parse_duration("what is the weather") is None
    assert _parse_duration("") is None


def test_zero_seconds_not_matched():
    result = _parse_duration("timer for 0 minutes")
    assert result is None


def test_bare_number_no_trigger_not_matched():
    result = _parse_duration("90s")
    assert result is None


def test_compound_1h30m_shorthand():
    result = _parse_duration("1h30m")
    assert result is not None
    assert result[0] == 5400


# ── Timer skill routing integration ──────────────────────────────────────────

def _make_skill_kwargs(**overrides):
    from jarvis.skill_utils import run_cmd, disk_usage, format_bytes, parse_meminfo, parse_ping, tail_lines, ensure_service_allowed
    kwargs = dict(
        role="admin",
        token=None,
        granted_permissions=[],
        emergency_stop_enabled=lambda: False,
        permission_check=lambda *a, **kw: True,
        run_cmd=run_cmd,
        disk_usage=disk_usage,
        format_bytes=format_bytes,
        parse_meminfo=parse_meminfo,
        parse_ping=parse_ping,
        tail_lines=tail_lines,
        ensure_service_allowed=ensure_service_allowed,
        proxmox_vm_status=lambda *a, **kw: {},
        proxmox_lxc_status=lambda *a, **kw: {},
        proxmox_vm_action=lambda *a, **kw: {},
        proxmox_lxc_action=lambda *a, **kw: {},
    )
    kwargs.update(overrides)
    return kwargs


def test_timer_skill_en_returns_reminder_route():
    from jarvis.assistant_domain import try_skill
    result = try_skill("set a timer for 20 minutes", **_make_skill_kwargs())
    assert result is not None
    assert result["data"]["route"] == "reminder"
    assert result["data"]["delay_ms"] == 1200000


def test_timer_skill_en_compound():
    from jarvis.assistant_domain import try_skill
    result = try_skill("timer 1h30m", **_make_skill_kwargs())
    assert result is not None
    assert result["data"]["delay_ms"] == 5400000


def test_timer_skill_de():
    from jarvis.assistant_domain import try_skill
    result = try_skill("timer für 5 minuten", **_make_skill_kwargs())
    assert result is not None
    assert result["data"]["route"] == "reminder"
    assert result["data"]["delay_ms"] == 300000


def test_timer_skill_with_label():
    from jarvis.assistant_domain import try_skill
    result = try_skill("remind me in 20 minutes to check the server", **_make_skill_kwargs())
    assert result is not None
    assert "check the server" in result["data"]["label"]
    assert "check the server" in result["reply"]
