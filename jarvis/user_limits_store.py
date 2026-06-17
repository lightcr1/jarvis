import json
import os
import time
from pathlib import Path

DEFAULT_LIMITS: dict = {
    "chf_per_day": 0.0,          # 0 = unlimited
    "chf_per_month": 0.0,
    "tokens_per_request": 0,      # 0 = use provider default
    "requests_per_min": 30,
    "expensive_models_per_day": 0,  # 0 = unlimited
    "allowed_models": [],           # empty = all allowed
    "updated_at": 0,
}


class UserLimitsStore:
    """Per-user spending and access limits (mirrors UserPreferencesStore pattern)."""

    def __init__(self) -> None:
        path_str = os.getenv("JARVIS_USER_LIMITS_STORE_PATH") or ""
        if path_str:
            self.path = Path(path_str)
        else:
            self.path = Path("/var/lib/jarvis/user_limits.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _empty(self) -> dict:
        return {"limits": {}}

    def _load(self) -> dict:
        try:
            content = json.loads(self.path.read_text(encoding="utf-8"))
            return {**self._empty(), **content}
        except (OSError, json.JSONDecodeError):
            return self._empty()

    def _save(self) -> None:
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _normalize(self, raw: dict) -> dict:
        out = {**DEFAULT_LIMITS}
        if "chf_per_day" in raw:
            out["chf_per_day"] = max(0.0, float(raw["chf_per_day"] or 0))
        if "chf_per_month" in raw:
            out["chf_per_month"] = max(0.0, float(raw["chf_per_month"] or 0))
        if "tokens_per_request" in raw:
            out["tokens_per_request"] = max(0, int(raw["tokens_per_request"] or 0))
        if "requests_per_min" in raw:
            out["requests_per_min"] = max(1, min(int(raw["requests_per_min"] or 30), 300))
        if "expensive_models_per_day" in raw:
            out["expensive_models_per_day"] = max(0, int(raw["expensive_models_per_day"] or 0))
        if "allowed_models" in raw:
            models = raw["allowed_models"]
            if isinstance(models, list):
                out["allowed_models"] = [str(m) for m in models if str(m).strip()]
            else:
                out["allowed_models"] = []
        out["updated_at"] = int(raw.get("updated_at") or 0)
        return out

    def get(self, user_id: str) -> dict:
        raw = self.data["limits"].get(user_id) or {}
        return self._normalize({**DEFAULT_LIMITS, **raw})

    def update(self, user_id: str, payload: dict) -> dict:
        current = self.get(user_id)
        merged = {**current, **{k: v for k, v in payload.items() if v is not None}}
        normalized = self._normalize(merged)
        normalized["updated_at"] = int(time.time())
        self.data["limits"][user_id] = normalized
        self._save()
        return normalized

    def delete(self, user_id: str) -> bool:
        existed = user_id in self.data["limits"]
        self.data["limits"].pop(user_id, None)
        if existed:
            self._save()
        return existed
