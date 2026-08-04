from __future__ import annotations

import json
import os
from pathlib import Path
import time


DEFAULT_PREFERENCES = {
    "display_name": "",
    "accent_color": "cyan",
    "auto_play_voice": True,
    "compact_mode": False,
    "orb_detail": "high",
    "theme": "dark",
    "location": "",
    "notes": [],
    "tts_voice": "",  # empty = use server default (EDGE_TTS_VOICE env var)
    "morning_briefing_enabled": False,
    "morning_briefing_time": "07:30",
    "quick_actions": ["Briefing", "System status", "Weather"],
    "notifications_enabled": True,
    "persona_tone": "formal",
    "response_language": "en",
    "quiet_hours_enabled": False,
    "quiet_hours_start": "22:00",
    "quiet_hours_end": "07:00",
    "weekly_digest_enabled": False,
    "weekly_digest_day": "sunday",
    "weekly_digest_time": "18:00",
    "nightly_summary_enabled": False,
    "nightly_summary_time": "21:00",
    "last_briefing_seen_ts": 0,
}

_WEEKDAY_NAMES = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}


def _validate_weekday(value: object, fallback: str) -> str:
    candidate = str(value).strip().lower()
    return candidate if candidate in _WEEKDAY_NAMES else fallback


def _validate_hm(value: object, fallback: str) -> str:
    text = str(value).strip()
    parts = text.split(":")
    if len(parts) != 2:
        return fallback
    try:
        hour, minute = int(parts[0]), int(parts[1])
    except ValueError:
        return fallback
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return fallback
    return f"{hour:02d}:{minute:02d}"


def is_within_quiet_hours(now_hm: str, start_hm: str, end_hm: str) -> bool:
    try:
        now_h, now_m = (int(p) for p in now_hm.split(":"))
        start_h, start_m = (int(p) for p in start_hm.split(":"))
        end_h, end_m = (int(p) for p in end_hm.split(":"))
    except (ValueError, AttributeError):
        return False
    now, start, end = now_h * 60 + now_m, start_h * 60 + start_m, end_h * 60 + end_m
    if start == end:
        return False
    if start < end:
        return start <= now < end
    return now >= start or now < end  # overnight range, e.g. 22:00 -> 07:00


def time_of_day_bucket(hour: int) -> str:
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 18:
        return "day"
    if 18 <= hour < 22:
        return "evening"
    return "night"

# Curated voices — best options for J.A.R.V.I.S. feel
JARVIS_VOICES = [
    {"id": "",                        "name": "Server default",                   "lang": "",      "flag": "⚙️"},
    {"id": "en-GB-RyanNeural",        "name": "Ryan — British Male",              "lang": "en-GB", "flag": "🇬🇧"},
    {"id": "en-GB-ThomasNeural",      "name": "Thomas — British Male",            "lang": "en-GB", "flag": "🇬🇧"},
    {"id": "en-GB-ElliotNeural",      "name": "Elliot — British Male",            "lang": "en-GB", "flag": "🇬🇧"},
    {"id": "en-GB-LibbyNeural",       "name": "Libby — British Female",           "lang": "en-GB", "flag": "🇬🇧"},
    {"id": "en-GB-SoniaNeural",       "name": "Sonia — British Female",           "lang": "en-GB", "flag": "🇬🇧"},
    {"id": "en-US-GuyNeural",         "name": "Guy — American Male",              "lang": "en-US", "flag": "🇺🇸"},
    {"id": "en-US-EricNeural",        "name": "Eric — American Male",             "lang": "en-US", "flag": "🇺🇸"},
    {"id": "en-US-BrianNeural",       "name": "Brian — American Male",            "lang": "en-US", "flag": "🇺🇸"},
    {"id": "en-AU-WilliamNeural",     "name": "William — Australian Male",        "lang": "en-AU", "flag": "🇦🇺"},
    {"id": "de-DE-ConradNeural",      "name": "Conrad — German Male",             "lang": "de-DE", "flag": "🇩🇪"},
    {"id": "de-DE-KillianNeural",     "name": "Killian — German Male",            "lang": "de-DE", "flag": "🇩🇪"},
]


class UserPreferencesStore:
    def __init__(self) -> None:
        configured = os.getenv("JARVIS_USER_PREFERENCES_PATH")
        if configured:
            self.path = Path(configured)
        else:
            user_store_path = os.getenv("JARVIS_USER_STORE_PATH")
            if user_store_path:
                self.path = Path(user_store_path).resolve().parent / "user_preferences.json"
            else:
                self.path = Path("/var/lib/jarvis/user_preferences.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _empty(self) -> dict:
        return {"preferences": {}}

    def _load(self) -> dict:
        if not self.path.exists():
            return self._empty()
        try:
            content = json.loads(self.path.read_text(encoding="utf-8"))
            return {**self._empty(), **content}
        except (OSError, json.JSONDecodeError):
            return self._empty()

    def _save(self) -> None:
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def get(self, user_id: str) -> dict:
        stored = self.data.get("preferences", {}).get(user_id, {})
        return {**DEFAULT_PREFERENCES, **stored}

    def update(self, user_id: str, payload: dict) -> dict:
        current = self.get(user_id)
        merged = {
            **current,
            "display_name": str(payload.get("display_name", current["display_name"])).strip(),
            "accent_color": str(payload.get("accent_color", current["accent_color"])).strip() or current["accent_color"],
            "auto_play_voice": bool(payload.get("auto_play_voice", current["auto_play_voice"])),
            "compact_mode": bool(payload.get("compact_mode", current["compact_mode"])),
            "orb_detail": str(payload.get("orb_detail", current["orb_detail"])).strip() or current["orb_detail"],
            "theme": "light" if str(payload.get("theme", current["theme"])).strip() == "light" else "dark",
            "location": str(payload.get("location", current.get("location", ""))).strip(),
            "notes": list(payload.get("notes", current.get("notes") or [])),
            "tts_voice": str(payload.get("tts_voice", current.get("tts_voice", ""))).strip(),
            "morning_briefing_enabled": bool(payload.get("morning_briefing_enabled", current.get("morning_briefing_enabled", False))),
            "morning_briefing_time": str(payload.get("morning_briefing_time", current.get("morning_briefing_time", "07:30"))).strip() or "07:30",
            "quick_actions": list(payload.get("quick_actions", current.get("quick_actions") or ["Briefing", "System status", "Weather"])),
            "notifications_enabled": bool(payload.get("notifications_enabled", current.get("notifications_enabled", True))),
            "persona_tone": str(payload.get("persona_tone", current.get("persona_tone", "formal"))).strip() if str(payload.get("persona_tone", current.get("persona_tone", "formal"))) in {"formal", "casual"} else "formal",
            "response_language": str(payload.get("response_language", current.get("response_language", "en"))).strip() if str(payload.get("response_language", current.get("response_language", "en"))) in {"en", "de"} else "en",
            "quiet_hours_enabled": bool(payload.get("quiet_hours_enabled", current.get("quiet_hours_enabled", False))),
            "quiet_hours_start": _validate_hm(payload.get("quiet_hours_start", current.get("quiet_hours_start", "22:00")), current.get("quiet_hours_start", "22:00")),
            "quiet_hours_end": _validate_hm(payload.get("quiet_hours_end", current.get("quiet_hours_end", "07:00")), current.get("quiet_hours_end", "07:00")),
            "weekly_digest_enabled": bool(payload.get("weekly_digest_enabled", current.get("weekly_digest_enabled", False))),
            "weekly_digest_day": _validate_weekday(payload.get("weekly_digest_day", current.get("weekly_digest_day", "sunday")), current.get("weekly_digest_day", "sunday")),
            "weekly_digest_time": _validate_hm(payload.get("weekly_digest_time", current.get("weekly_digest_time", "18:00")), current.get("weekly_digest_time", "18:00")),
            "nightly_summary_enabled": bool(payload.get("nightly_summary_enabled", current.get("nightly_summary_enabled", False))),
            "nightly_summary_time": _validate_hm(payload.get("nightly_summary_time", current.get("nightly_summary_time", "21:00")), current.get("nightly_summary_time", "21:00")),
            "updated_at": int(time.time()),
        }
        self.data.setdefault("preferences", {})[user_id] = merged
        self._save()
        return merged

    def mark_briefing_seen(self, user_id: str, ts: int | None = None) -> dict:
        current = self.get(user_id)
        current["last_briefing_seen_ts"] = ts if ts is not None else int(time.time())
        current["updated_at"] = int(time.time())
        self.data.setdefault("preferences", {})[user_id] = current
        self._save()
        return current

    def delete(self, user_id: str) -> bool:
        removed = self.data.setdefault("preferences", {}).pop(user_id, None)
        if removed is not None:
            self._save()
            return True
        return False
