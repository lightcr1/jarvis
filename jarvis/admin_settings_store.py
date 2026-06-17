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
                "wakeword_engine": "software",
                "wakeword_sensitivity": 0.5,
                "stt_provider": "local",
            },
            "home_assistant": {
                "confirmation_ttl_sec": 300,
                "remote_allowed_cidrs": [],
            },
            "provider": {
                "default_provider": "openrouter",
                "openrouter_enabled": True,
                "usd_to_chf_rate": 0.90,
                "model_prices": {},
                "global_daily_budget_chf": 0.0,
                "global_monthly_budget_chf": 0.0,
                "kill_switch": False,
                "disable_expensive_models": False,
                "expensive_threshold_chf": 0.10,
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
        provider_raw = candidate.get("provider")
        if not isinstance(provider_raw, dict):
            provider_raw = {}

        token_ttl_raw = usage_limits.get("token_ttl_min", base["usage_limits"]["token_ttl_min"])
        max_active_raw = usage_limits.get("max_active_tokens", base["usage_limits"]["max_active_tokens"])
        wakeword_enabled_raw = voice.get("wakeword_enabled", base["voice"]["wakeword_enabled"])
        wakeword_phrase_raw = voice.get("wakeword_phrase", base["voice"]["wakeword_phrase"])
        wakeword_engine_raw = voice.get("wakeword_engine", base["voice"]["wakeword_engine"])
        wakeword_sensitivity_raw = voice.get("wakeword_sensitivity", base["voice"]["wakeword_sensitivity"])
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
        wakeword_engine = (str(wakeword_engine_raw or "").strip().lower() or base["voice"]["wakeword_engine"])
        if wakeword_engine not in {"software", "openwakeword", "none"}:
            wakeword_engine = base["voice"]["wakeword_engine"]
        try:
            wakeword_sensitivity = float(wakeword_sensitivity_raw)
            wakeword_sensitivity = max(0.0, min(1.0, wakeword_sensitivity))
        except (TypeError, ValueError):
            wakeword_sensitivity = base["voice"]["wakeword_sensitivity"]
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

        # Provider section normalization
        bp = base["provider"]
        _KNOWN_PROVIDERS = {"openrouter", "anthropic", "openai", "gemini", "mistral", "deepseek", "local"}
        default_provider = str(provider_raw.get("default_provider") or bp["default_provider"]).strip().lower()
        if default_provider not in _KNOWN_PROVIDERS:
            default_provider = bp["default_provider"]
        try:
            usd_to_chf_rate = float(provider_raw.get("usd_to_chf_rate") or bp["usd_to_chf_rate"])
            if usd_to_chf_rate <= 0:
                usd_to_chf_rate = bp["usd_to_chf_rate"]
        except (TypeError, ValueError):
            usd_to_chf_rate = bp["usd_to_chf_rate"]
        model_prices_raw = provider_raw.get("model_prices", bp["model_prices"])
        model_prices = {}
        if isinstance(model_prices_raw, dict):
            for k, v in model_prices_raw.items():
                if isinstance(v, dict):
                    try:
                        model_prices[str(k)] = {
                            "in": max(0.0, float(v.get("in", 0))),
                            "out": max(0.0, float(v.get("out", 0))),
                            "tier": str(v.get("tier", "medium")),
                            "expensive": bool(v.get("expensive", False)),
                        }
                    except (TypeError, ValueError):
                        pass
        try:
            global_daily_budget_chf = max(0.0, float(provider_raw.get("global_daily_budget_chf") or 0))
        except (TypeError, ValueError):
            global_daily_budget_chf = bp["global_daily_budget_chf"]
        try:
            global_monthly_budget_chf = max(0.0, float(provider_raw.get("global_monthly_budget_chf") or 0))
        except (TypeError, ValueError):
            global_monthly_budget_chf = bp["global_monthly_budget_chf"]
        try:
            expensive_threshold_chf = max(0.0, float(provider_raw.get("expensive_threshold_chf") or bp["expensive_threshold_chf"]))
        except (TypeError, ValueError):
            expensive_threshold_chf = bp["expensive_threshold_chf"]

        return {
            "usage_limits": {
                "token_ttl_min": token_ttl_min,
                "max_active_tokens": max_active_tokens,
            },
            "voice": {
                "wakeword_enabled": bool(wakeword_enabled_raw),
                "wakeword_phrase": wakeword_phrase,
                "wakeword_engine": wakeword_engine,
                "wakeword_sensitivity": wakeword_sensitivity,
                "stt_provider": stt_provider,
            },
            "home_assistant": {
                "confirmation_ttl_sec": confirmation_ttl_sec,
                "remote_allowed_cidrs": normalized_cidrs,
            },
            "provider": {
                "default_provider": default_provider,
                "openrouter_enabled": bool(provider_raw.get("openrouter_enabled", bp["openrouter_enabled"])),
                "usd_to_chf_rate": usd_to_chf_rate,
                "model_prices": model_prices,
                "global_daily_budget_chf": global_daily_budget_chf,
                "global_monthly_budget_chf": global_monthly_budget_chf,
                "kill_switch": bool(provider_raw.get("kill_switch", bp["kill_switch"])),
                "disable_expensive_models": bool(provider_raw.get("disable_expensive_models", bp["disable_expensive_models"])),
                "expensive_threshold_chf": expensive_threshold_chf,
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
        provider = payload.get("provider")
        if isinstance(provider, dict):
            current_provider = merged.get("provider") or {}
            current_provider.update(provider)
            merged["provider"] = current_provider
        self.data = self._normalize(merged)
        self._save()
        return self.get()
