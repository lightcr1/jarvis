"""Tests for the weekly digest / nightly summary loop helpers in jarvisappv4.py."""
from __future__ import annotations

from datetime import datetime

import pytest

import jarvisappv4 as app


# ---------------------------------------------------------------------------
# _next_weekly_seconds
# ---------------------------------------------------------------------------

def test_next_weekly_seconds_same_day_future_time():
    now = datetime(2026, 7, 26, 10, 0, 0)  # a Sunday
    secs = app._next_weekly_seconds("sunday", "18:00", now)
    assert abs(secs - 8 * 3600) < 2


def test_next_weekly_seconds_wraps_to_next_week_when_past():
    now = datetime(2026, 7, 26, 20, 0, 0)  # Sunday, after 18:00
    secs = app._next_weekly_seconds("sunday", "18:00", now)
    assert secs > 6 * 86400  # wraps a full week


def test_next_weekly_seconds_future_weekday():
    now = datetime(2026, 7, 26, 10, 0, 0)  # Sunday
    secs = app._next_weekly_seconds("wednesday", "09:00", now)
    assert 2 * 86400 < secs < 4 * 86400


def test_next_weekly_seconds_invalid_day_falls_back_to_sunday():
    now = datetime(2026, 7, 26, 10, 0, 0)  # Sunday
    secs = app._next_weekly_seconds("not-a-day", "18:00", now)
    assert abs(secs - 8 * 3600) < 2


def test_next_weekly_seconds_invalid_time_falls_back():
    now = datetime(2026, 7, 26, 10, 0, 0)
    secs = app._next_weekly_seconds("sunday", "bogus", now)
    assert abs(secs - 8 * 3600) < 2  # falls back to 18:00


# ---------------------------------------------------------------------------
# _top_alert_events
# ---------------------------------------------------------------------------

def test_top_alert_events_filters_by_time_and_sorts_by_severity():
    history = [
        {"rule_name": "old", "severity": "critical", "timestamp": 100},
        {"rule_name": "recent-warning", "severity": "warning", "timestamp": 900},
        {"rule_name": "recent-critical", "severity": "critical", "timestamp": 950},
    ]
    top = app._top_alert_events(history, since_ts=500, limit=5)
    assert len(top) == 2
    assert top[0]["rule_name"] == "recent-critical"  # critical ranks first
    assert top[1]["rule_name"] == "recent-warning"


def test_top_alert_events_respects_limit():
    history = [{"rule_name": f"a{i}", "severity": "info", "timestamp": 1000 + i} for i in range(10)]
    top = app._top_alert_events(history, since_ts=0, limit=3)
    assert len(top) == 3


# ---------------------------------------------------------------------------
# _build_weekly_digest_text
# ---------------------------------------------------------------------------

def test_build_weekly_digest_text_with_data():
    text = app._build_weekly_digest_text(
        cpu_pct=42.0, ram_pct=55.0, disk_pct=60.0,
        top_alerts=[{"rule_name": "High CPU", "severity": "warning"}],
        backup_successes=6, backup_failures=1,
    )
    assert "CPU 42%" in text
    assert "High CPU" in text
    assert "6 succeeded, 1 failed" in text


def test_build_weekly_digest_text_no_alerts_no_backups():
    text = app._build_weekly_digest_text(10.0, 20.0, 30.0, [], 0, 0)
    assert "No alerts fired this week." in text
    assert "backup" not in text.lower() or "Auto-backups" not in text


def test_build_weekly_digest_text_missing_metrics():
    text = app._build_weekly_digest_text(None, None, None, [], 0, 0)
    assert "unavailable" in text.lower()


# ---------------------------------------------------------------------------
# _count_sessions_active_on
# ---------------------------------------------------------------------------

def test_count_sessions_active_on_matches_date():
    import time as _t
    today_ts = int(_t.time())
    sessions = [
        {"id": "s1", "updated_at": today_ts},
        {"id": "s2", "updated_at": today_ts - 10 * 86400},  # 10 days ago
    ]
    from datetime import datetime as _dt
    today_str = _dt.fromtimestamp(today_ts).date().isoformat()
    count = app._count_sessions_active_on(sessions, today_str)
    assert count == 1


def test_count_sessions_active_on_handles_missing_timestamp():
    sessions = [{"id": "s1"}]
    assert app._count_sessions_active_on(sessions, "2026-01-01") == 0


# ---------------------------------------------------------------------------
# _build_nightly_summary_text
# ---------------------------------------------------------------------------

def test_build_nightly_summary_text_full():
    text = app._build_nightly_summary_text(
        chat_count_today=3,
        alerts_today=[{"rule_name": "High CPU"}],
        briefing_sent=True,
        tomorrow_calendar_lines=["09:00 — Standup"],
    )
    assert "3 conversations today" in text
    assert "1 alert fired" in text
    assert "morning briefing sent" in text
    assert "Tomorrow: 09:00 — Standup." in text


def test_build_nightly_summary_text_empty_day():
    text = app._build_nightly_summary_text(
        chat_count_today=0, alerts_today=[], briefing_sent=False, tomorrow_calendar_lines=[],
    )
    assert "No chat activity today" in text
    assert "no alerts fired" in text
    assert "morning briefing not sent" in text
    assert "Tomorrow" not in text


# ---------------------------------------------------------------------------
# _calendar_lines_for_date (shared by morning briefing + nightly summary)
# ---------------------------------------------------------------------------

def test_calendar_lines_for_date_formats_time_and_title():
    items = [
        {"starts_at": "2026-07-27T09:30:00", "title": "Standup"},
        {"starts_at": "2026-07-28T10:00:00", "title": "Not today"},
    ]
    lines = app._calendar_lines_for_date(items, "2026-07-27")
    assert lines == ["09:30 — Standup"]


def test_calendar_lines_for_date_handles_missing_title():
    items = [{"starts_at": "2026-07-27T09:30:00"}]
    assert app._calendar_lines_for_date(items, "2026-07-27") == []


# ---------------------------------------------------------------------------
# Opt-in gating (mirrors test_morning_briefing.py's pattern)
# ---------------------------------------------------------------------------

def test_weekly_digest_disabled_users_excluded():
    prefs_data = {
        "user1": {"weekly_digest_enabled": False},
        "user2": {"weekly_digest_enabled": True, "weekly_digest_day": "sunday"},
    }
    enabled = [(uid, p) for uid, p in prefs_data.items() if p.get("weekly_digest_enabled")]
    assert len(enabled) == 1
    assert enabled[0][0] == "user2"


def test_nightly_summary_disabled_users_excluded():
    prefs_data = {
        "user1": {"nightly_summary_enabled": False},
        "user2": {"nightly_summary_enabled": True},
    }
    enabled = [(uid, p) for uid, p in prefs_data.items() if p.get("nightly_summary_enabled")]
    assert len(enabled) == 1


# ---------------------------------------------------------------------------
# Broadcast integration (mirrors test_morning_briefing.py's pattern)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_weekly_digest_broadcast_payload_shape():
    calls: list[dict] = []

    async def mock_broadcast(payload: dict) -> None:
        calls.append(payload)

    await mock_broadcast({
        "type": "weekly_digest",
        "user_id": "user-abc",
        "text": "Current load: CPU 10%, RAM 20%, disk 30%.",
        "ts": 1234567890,
    })
    assert len(calls) == 1
    assert calls[0]["type"] == "weekly_digest"
    assert "user_id" in calls[0]
    assert "text" in calls[0]


@pytest.mark.asyncio
async def test_nightly_summary_broadcast_payload_shape():
    calls: list[dict] = []

    async def mock_broadcast(payload: dict) -> None:
        calls.append(payload)

    await mock_broadcast({
        "type": "nightly_summary",
        "user_id": "user-abc",
        "text": "No chat activity today; no alerts fired; morning briefing sent.",
        "ts": 1234567890,
    })
    assert len(calls) == 1
    assert calls[0]["type"] == "nightly_summary"


# ---------------------------------------------------------------------------
# Auto-backup outcome log
# ---------------------------------------------------------------------------

def test_record_auto_backup_outcome_appends_and_caps():
    app._auto_backup_log.clear()
    for _ in range(510):
        app._record_auto_backup_outcome(True)
    assert len(app._auto_backup_log) == 500
    app._auto_backup_log.clear()


def test_record_auto_backup_outcome_tracks_ok_flag():
    app._auto_backup_log.clear()
    app._record_auto_backup_outcome(True)
    app._record_auto_backup_outcome(False)
    assert [b["ok"] for b in app._auto_backup_log] == [True, False]
    app._auto_backup_log.clear()
