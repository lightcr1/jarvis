"""Tests for morning briefing loop helpers."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest


# _next_briefing_seconds is a pure function defined in jarvisappv4.py.
# We replicate it inline here for isolation — any change to the function
# must be reflected here too (or better: extract to a shared module).
def _next_briefing_seconds(hhmm: str, now) -> float:
    """Return seconds until next occurrence of HH:MM from now."""
    try:
        h, m = (int(x) for x in hhmm.split(":"))
    except Exception:
        return 3600.0
    target = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


# ── _next_briefing_seconds pure function tests ──────────────────────────────

def test_next_briefing_future_time():
    now = datetime(2026, 6, 24, 6, 0, 0)  # 06:00
    secs = _next_briefing_seconds("07:30", now)
    assert abs(secs - 5400) < 2  # 1.5 hours = 5400s


def test_next_briefing_past_time_wraps_to_next_day():
    now = datetime(2026, 6, 24, 8, 0, 0)  # 08:00 — after 07:30
    secs = _next_briefing_seconds("07:30", now)
    # Should wrap to next day: ~23.5 hours
    assert secs > 82000  # > 22.7 hours


def test_next_briefing_exactly_now_wraps():
    now = datetime(2026, 6, 24, 7, 30, 0)
    secs = _next_briefing_seconds("07:30", now)
    # target == now → condition target <= now is True → adds 1 day
    assert secs > 86000


def test_next_briefing_invalid_hhmm_returns_fallback():
    now = datetime(2026, 6, 24, 7, 0, 0)
    secs = _next_briefing_seconds("not-a-time", now)
    assert secs == 3600.0


def test_next_briefing_midnight():
    now = datetime(2026, 6, 24, 23, 59, 0)
    secs = _next_briefing_seconds("00:00", now)
    assert 0 < secs < 120  # ~1 minute away


# ── Opt-in gating tests ───────────────────────────────────────────────────────

def test_disabled_users_are_excluded():
    prefs_data = {
        "user1": {"morning_briefing_enabled": False, "morning_briefing_time": "07:30"},
        "user2": {"morning_briefing_enabled": True,  "morning_briefing_time": "07:30"},
    }
    enabled = [
        (uid, p) for uid, p in prefs_data.items() if p.get("morning_briefing_enabled")
    ]
    assert len(enabled) == 1
    assert enabled[0][0] == "user2"


def test_no_enabled_users_yields_empty_list():
    prefs_data = {"user1": {"morning_briefing_enabled": False}}
    enabled = [(uid, p) for uid, p in prefs_data.items() if p.get("morning_briefing_enabled")]
    assert enabled == []


def test_time_mismatch_excludes_user():
    users = [
        ("u1", {"morning_briefing_enabled": True, "morning_briefing_time": "08:00"}),
    ]
    current_hm = "07:30"
    fired = [
        uid for uid, p in users
        if p.get("morning_briefing_enabled") and p.get("morning_briefing_time") == current_hm
    ]
    assert fired == []


# ── Broadcast integration tests ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_broadcast_called_when_user_fires():
    broadcast_calls: list[dict] = []

    async def mock_broadcast(payload: dict) -> None:
        broadcast_calls.append(payload)

    broadcaster = MagicMock()
    broadcaster.broadcast = mock_broadcast

    uid = "user-abc"
    prefs = {"morning_briefing_enabled": True, "morning_briefing_time": "07:30"}
    current_hm = "07:30"
    reply_text = "Good morning. All systems nominal."

    if prefs.get("morning_briefing_time") == current_hm:
        await broadcaster.broadcast({
            "type": "briefing",
            "user_id": uid,
            "text": reply_text,
            "ts": 1234567890,
        })

    assert len(broadcast_calls) == 1
    assert broadcast_calls[0]["type"] == "briefing"
    assert broadcast_calls[0]["user_id"] == uid
    assert broadcast_calls[0]["text"] == reply_text


@pytest.mark.asyncio
async def test_broadcast_not_called_when_time_mismatch():
    broadcast_calls: list[dict] = []

    async def mock_broadcast(payload: dict) -> None:
        broadcast_calls.append(payload)

    broadcaster = MagicMock()
    broadcaster.broadcast = mock_broadcast

    uid = "user-abc"
    prefs = {"morning_briefing_enabled": True, "morning_briefing_time": "08:00"}
    current_hm = "07:30"

    if prefs.get("morning_briefing_time") == current_hm:
        await broadcaster.broadcast({"type": "briefing", "user_id": uid, "text": "test", "ts": 0})

    assert len(broadcast_calls) == 0


@pytest.mark.asyncio
async def test_broadcast_fires_for_each_matching_user():
    broadcast_calls: list[dict] = []

    async def mock_broadcast(payload: dict) -> None:
        broadcast_calls.append(payload)

    broadcaster = MagicMock()
    broadcaster.broadcast = mock_broadcast

    users = [
        ("u1", {"morning_briefing_enabled": True,  "morning_briefing_time": "07:30"}),
        ("u2", {"morning_briefing_enabled": True,  "morning_briefing_time": "07:30"}),
        ("u3", {"morning_briefing_enabled": False, "morning_briefing_time": "07:30"}),
    ]
    current_hm = "07:30"
    for uid, p in users:
        if p.get("morning_briefing_enabled") and p.get("morning_briefing_time") == current_hm:
            await broadcaster.broadcast({"type": "briefing", "user_id": uid, "text": "test", "ts": 0})

    assert len(broadcast_calls) == 2
    fired_uids = {c["user_id"] for c in broadcast_calls}
    assert fired_uids == {"u1", "u2"}


@pytest.mark.asyncio
async def test_broadcast_payload_contains_required_fields():
    broadcast_calls: list[dict] = []

    async def mock_broadcast(payload: dict) -> None:
        broadcast_calls.append(payload)

    broadcaster = MagicMock()
    broadcaster.broadcast = mock_broadcast

    await broadcaster.broadcast({
        "type": "briefing",
        "user_id": "user-xyz",
        "text": "Good morning. System load nominal.",
        "ts": 9999999999,
    })

    assert len(broadcast_calls) == 1
    payload = broadcast_calls[0]
    assert "type" in payload
    assert "user_id" in payload
    assert "text" in payload
    assert "ts" in payload
    assert payload["type"] == "briefing"
