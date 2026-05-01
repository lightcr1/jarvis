from __future__ import annotations

import json
import os
import time
from pathlib import Path


class HomeAssistantStore:
    def __init__(self) -> None:
        configured = os.getenv("JARVIS_HOME_ASSISTANT_STORE_PATH")
        self.path = Path(configured) if configured else Path("/var/lib/jarvis/home_assistant.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _empty(self) -> dict:
        return {
            "config": {"base_url": "", "enabled": False, "integration_mode": "scaffold"},
            "managed_entities": [],
            "discovery_candidates": [],
            "shopping_list_items": [],
            "calendar_items": [],
            "inbox_items": [],
            "system_targets": [],
            "control_requests": [],
            "automation_rules": [],
            "updated_at": 0,
        }

    def _load(self) -> dict:
        if not self.path.exists():
            return self._empty()
        try:
            content = json.loads(self.path.read_text(encoding="utf-8"))
            merged = {**self._empty(), **content}
            if not isinstance(merged.get("managed_entities"), list):
                merged["managed_entities"] = []
            if not isinstance(merged.get("discovery_candidates"), list):
                merged["discovery_candidates"] = []
            if not isinstance(merged.get("shopping_list_items"), list):
                merged["shopping_list_items"] = []
            if not isinstance(merged.get("calendar_items"), list):
                merged["calendar_items"] = []
            if not isinstance(merged.get("inbox_items"), list):
                merged["inbox_items"] = []
            if not isinstance(merged.get("system_targets"), list):
                merged["system_targets"] = []
            if not isinstance(merged.get("control_requests"), list):
                merged["control_requests"] = []
            if not isinstance(merged.get("automation_rules"), list):
                merged["automation_rules"] = []
            return merged
        except (OSError, json.JSONDecodeError):
            return self._empty()

    def _save(self) -> None:
        self.data["updated_at"] = int(time.time())
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_config(self) -> dict:
        return dict(self.data.get("config", {}))

    def list_managed_entities(self) -> list[dict]:
        return list(self.data.get("managed_entities", []))

    def add_managed_entity(self, entity: dict) -> dict:
        self.data.setdefault("managed_entities", []).append(entity)
        self._save()
        return entity

    def get_managed_entity(self, entity_id: str) -> dict | None:
        for item in self.data.get("managed_entities", []):
            if item.get("entity_id") == entity_id:
                return dict(item)
        return None

    def update_managed_entity(self, entity_id: str, patch: dict) -> dict | None:
        entities = self.data.setdefault("managed_entities", [])
        for idx, item in enumerate(entities):
            if item.get("entity_id") != entity_id:
                continue
            updated = {**item, **patch}
            entities[idx] = updated
            self._save()
            return updated
        return None

    def list_discovery_candidates(self) -> list[dict]:
        return list(self.data.get("discovery_candidates", []))

    def get_discovery_candidate(self, candidate_id: str) -> dict | None:
        for item in self.data.get("discovery_candidates", []):
            if item.get("id") == candidate_id:
                return dict(item)
        return None

    def add_discovery_candidate(self, candidate: dict) -> dict:
        self.data.setdefault("discovery_candidates", []).append(candidate)
        self._save()
        return candidate

    def update_discovery_candidate(self, candidate_id: str, patch: dict) -> dict | None:
        candidates = self.data.setdefault("discovery_candidates", [])
        for idx, item in enumerate(candidates):
            if item.get("id") != candidate_id:
                continue
            updated = {**item, **patch}
            candidates[idx] = updated
            self._save()
            return updated
        return None

    def list_shopping_list_items(self) -> list[dict]:
        return list(self.data.get("shopping_list_items", []))

    def add_shopping_list_item(self, item: dict) -> dict:
        self.data.setdefault("shopping_list_items", []).append(item)
        self._save()
        return item

    def list_calendar_items(self) -> list[dict]:
        return list(self.data.get("calendar_items", []))

    def add_calendar_item(self, item: dict) -> dict:
        self.data.setdefault("calendar_items", []).append(item)
        self._save()
        return item

    def get_calendar_item(self, item_id: str) -> dict | None:
        for item in self.data.get("calendar_items", []):
            if item.get("id") == item_id:
                return dict(item)
        return None

    def update_calendar_item(self, item_id: str, patch: dict) -> dict | None:
        items = self.data.setdefault("calendar_items", [])
        for idx, item in enumerate(items):
            if item.get("id") != item_id:
                continue
            updated = {**item, **patch}
            items[idx] = updated
            self._save()
            return updated
        return None

    def replace_calendar_items(self, items: list[dict]) -> list[dict]:
        self.data["calendar_items"] = list(items)
        self._save()
        return list(self.data["calendar_items"])

    def list_inbox_items(self) -> list[dict]:
        return list(self.data.get("inbox_items", []))

    def add_inbox_item(self, item: dict) -> dict:
        self.data.setdefault("inbox_items", []).append(item)
        self._save()
        return item

    def get_inbox_item(self, item_id: str) -> dict | None:
        for item in self.data.get("inbox_items", []):
            if item.get("id") == item_id:
                return dict(item)
        return None

    def update_inbox_item(self, item_id: str, patch: dict) -> dict | None:
        items = self.data.setdefault("inbox_items", [])
        for idx, item in enumerate(items):
            if item.get("id") != item_id:
                continue
            updated = {**item, **patch}
            items[idx] = updated
            self._save()
            return updated
        return None

    def replace_inbox_items(self, items: list[dict]) -> list[dict]:
        self.data["inbox_items"] = list(items)
        self._save()
        return list(self.data["inbox_items"])

    def list_system_targets(self) -> list[dict]:
        return list(self.data.get("system_targets", []))

    def get_system_target(self, target_id: str) -> dict | None:
        for item in self.data.get("system_targets", []):
            if item.get("id") == target_id:
                return dict(item)
        return None

    def add_system_target(self, item: dict) -> dict:
        self.data.setdefault("system_targets", []).append(item)
        self._save()
        return item

    def update_system_target(self, target_id: str, patch: dict) -> dict | None:
        targets = self.data.setdefault("system_targets", [])
        for idx, item in enumerate(targets):
            if item.get("id") != target_id:
                continue
            updated = {**item, **patch}
            targets[idx] = updated
            self._save()
            return updated
        return None

    def list_control_requests(self) -> list[dict]:
        return list(self.data.get("control_requests", []))

    def get_control_request(self, request_id: str) -> dict | None:
        for item in self.data.get("control_requests", []):
            if item.get("id") == request_id:
                return dict(item)
        return None

    def add_control_request(self, item: dict) -> dict:
        self.data.setdefault("control_requests", []).append(item)
        self._save()
        return item

    def update_control_request(self, request_id: str, patch: dict) -> dict | None:
        requests = self.data.setdefault("control_requests", [])
        for idx, item in enumerate(requests):
            if item.get("id") != request_id:
                continue
            updated = {**item, **patch}
            requests[idx] = updated
            self._save()
            return updated
        return None

    def list_automation_rules(self) -> list[dict]:
        return list(self.data.get("automation_rules", []))

    def get_automation_rule(self, rule_id: str) -> dict | None:
        for item in self.data.get("automation_rules", []):
            if item.get("id") == rule_id:
                return dict(item)
        return None

    def add_automation_rule(self, item: dict) -> dict:
        self.data.setdefault("automation_rules", []).append(item)
        self._save()
        return item

    def update_automation_rule(self, rule_id: str, patch: dict) -> dict | None:
        rules = self.data.setdefault("automation_rules", [])
        for idx, item in enumerate(rules):
            if item.get("id") != rule_id:
                continue
            updated = {**item, **patch}
            rules[idx] = updated
            self._save()
            return updated
        return None
