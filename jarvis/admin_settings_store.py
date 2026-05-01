from __future__ import annotations

import json
import os
from pathlib import Path


class AdminSettingsStore:
    def __init__(self) -> None:
        configured = os.getenv("JARVIS_ADMIN_SETTINGS_PATH")
        self.path = Path(configured) if configured else Path("/var/lib/jarvis/admin_settings.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _empty(self) -> dict:
        return {
            "usage_limits": {
                "token_ttl_min": 20,
                "max_active_tokens": 200,
            },
            "voice": {
                "wakeword_enabled": False,
                "wakeword_phrase": "hey jarvis",
                "stt_provider": "local",
            },
            "home_assistant": {
                "confirmation_ttl_sec": 300,
                "remote_allowed_cidrs": [],
            },
        }

    def _normalize(self, payload: dict | None) -> dict:
        base = self._empty()
        candidate = payload if isinstance(payload, dict) else {}

        usage_limits = candidate.get("usage_limits")
        if not isinstance(usage_limits, dict):
            usage_limits = {}
        voice = candidate.get("voice")
        if not isinstance(voice, dict):
            voice = {}
        home_assistant = candidate.get("home_assistant")
        if not isinstance(home_assistant, dict):
            home_assistant = {}

        token_ttl_raw = usage_limits.get("token_ttl_min", base["usage_limits"]["token_ttl_min"])
        max_active_raw = usage_limits.get("max_active_tokens", base["usage_limits"]["max_active_tokens"])
        wakeword_enabled_raw = voice.get("wakeword_enabled", base["voice"]["wakeword_enabled"])
        wakeword_phrase_raw = voice.get("wakeword_phrase", base["voice"]["wakeword_phrase"])
        stt_provider_raw = voice.get("stt_provider", base["voice"]["stt_provider"])
        confirmation_ttl_raw = home_assistant.get("confirmation_ttl_sec", base["home_assistant"]["confirmation_ttl_sec"])
        remote_allowed_raw = home_assistant.get("remote_allowed_cidrs", base["home_assistant"]["remote_allowed_cidrs"])

        try:
            token_ttl_min = int(token_ttl_raw)
        except (TypeError, ValueError):
            token_ttl_min = base["usage_limits"]["token_ttl_min"]
        token_ttl_min = max(1, token_ttl_min)

        try:
            max_active_tokens = int(max_active_raw)
        except (TypeError, ValueError):
            max_active_tokens = base["usage_limits"]["max_active_tokens"]
        max_active_tokens = max(1, max_active_tokens)

        wakeword_phrase = (str(wakeword_phrase_raw or "").strip().lower() or base["voice"]["wakeword_phrase"])
        stt_provider = (str(stt_provider_raw or "").strip().lower() or base["voice"]["stt_provider"])
        if stt_provider not in {"local", "gemini"}:
            stt_provider = base["voice"]["stt_provider"]

        try:
            confirmation_ttl_sec = int(confirmation_ttl_raw)
        except (TypeError, ValueError):
            confirmation_ttl_sec = base["home_assistant"]["confirmation_ttl_sec"]
        confirmation_ttl_sec = max(30, confirmation_ttl_sec)

        remote_allowed_cidrs = remote_allowed_raw if isinstance(remote_allowed_raw, list) else []
        normalized_cidrs = []
        for item in remote_allowed_cidrs:
            cidr = str(item or "").strip()
            if cidr and cidr not in normalized_cidrs:
                normalized_cidrs.append(cidr)

        return {
            "usage_limits": {
                "token_ttl_min": token_ttl_min,
                "max_active_tokens": max_active_tokens,
            },
            "voice": {
                "wakeword_enabled": bool(wakeword_enabled_raw),
                "wakeword_phrase": wakeword_phrase,
                "stt_provider": stt_provider,
            },
            "home_assistant": {
                "confirmation_ttl_sec": confirmation_ttl_sec,
                "remote_allowed_cidrs": normalized_cidrs,
            },
        }

    def _load(self) -> dict:
        if not self.path.exists():
            return self._empty()
        try:
            content = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return self._empty()
        return self._normalize(content)

    def _save(self) -> None:
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def get(self) -> dict:
        return self._normalize(self.data)

    def update(self, payload: dict) -> dict:
        merged = self.get()
        usage_limits = payload.get("usage_limits")
        if isinstance(usage_limits, dict):
            merged["usage_limits"].update(usage_limits)
        voice = payload.get("voice")
        if isinstance(voice, dict):
            merged["voice"].update(voice)
        home_assistant = payload.get("home_assistant")
        if isinstance(home_assistant, dict):
            merged["home_assistant"].update(home_assistant)
        self.data = self._normalize(merged)
        self._save()
        return self.get()
