from __future__ import annotations

import os
import time
import uuid
from ipaddress import ip_address, ip_network

from .permissions import HOME_ASSISTANT_PERMISSION_GROUPS
from .risk import HOME_ASSISTANT_ACTION_POLICIES


class HomeAssistantAccessError(PermissionError):
    pass


DEVICE_ACTION_PROFILES: dict[str, dict[str, object]] = {
    "light": {
        "actions": [
            {"action": "turn_on", "label": "Turn on", "risk_level": "medium", "remote": False},
            {"action": "turn_off", "label": "Turn off", "risk_level": "medium", "remote": False},
        ]
    },
    "switch": {
        "actions": [
            {"action": "turn_on", "label": "Turn on", "risk_level": "medium", "remote": False},
            {"action": "turn_off", "label": "Turn off", "risk_level": "medium", "remote": False},
        ]
    },
    "sensor": {
        "actions": [],
    },
    "camera": {
        "actions": [
            {"action": "record", "label": "Start recording", "risk_level": "high", "remote": True},
            {"action": "stream", "label": "Request stream", "risk_level": "high", "remote": True},
        ]
    },
    "alarm": {
        "actions": [
            {"action": "arm", "label": "Arm", "risk_level": "high", "remote": True},
            {"action": "disarm", "label": "Disarm", "risk_level": "high", "remote": True},
        ]
    },
    "lock": {
        "actions": [
            {"action": "lock", "label": "Lock", "risk_level": "high", "remote": True},
            {"action": "unlock", "label": "Unlock", "risk_level": "high", "remote": True},
        ]
    },
    "garage_door": {
        "actions": [
            {"action": "open", "label": "Open", "risk_level": "high", "remote": True},
            {"action": "close", "label": "Close", "risk_level": "high", "remote": True},
        ]
    },
}

SYSTEM_TARGET_PROFILES: dict[str, dict[str, object]] = {
    "pc": {
        "actions": [
            {"action": "wake", "label": "Wake", "risk_level": "medium", "remote": False},
            {"action": "status_check", "label": "Status check", "risk_level": "low", "remote": False},
            {"action": "restart", "label": "Restart", "risk_level": "high", "remote": True},
            {"action": "shutdown", "label": "Shutdown", "risk_level": "high", "remote": True},
        ]
    },
    "server": {
        "actions": [
            {"action": "status_check", "label": "Status check", "risk_level": "low", "remote": False},
            {"action": "restart", "label": "Restart", "risk_level": "high", "remote": True},
        ]
    },
    "nas": {
        "actions": [
            {"action": "status_check", "label": "Status check", "risk_level": "low", "remote": False},
            {"action": "restart", "label": "Restart", "risk_level": "high", "remote": True},
        ]
    },
}

RECOVERY_PLAYBOOKS: tuple[dict[str, object], ...] = (
    {
        "id": "sync_entities",
        "title": "Refresh entity states",
        "description": "Run a state sync against the configured Home Assistant backend.",
        "required_permission": "home_assistant.access",
        "risk_level": "low",
    },
    {
        "id": "review_pending_confirmations",
        "title": "Review pending confirmations",
        "description": "Inspect queued control requests before any high-risk action is completed.",
        "required_permission": "home_assistant.access",
        "risk_level": "low",
    },
    {
        "id": "disable_automations",
        "title": "Disable all automations",
        "description": "Emergency brake for staged Jarvis-managed automations.",
        "required_permission": "home_assistant.automation_management",
        "risk_level": "medium",
    },
    {
        "id": "sync_personal_assistant_data",
        "title": "Refresh calendar and inbox",
        "description": "Pull the latest scaffolded calendar and inbox items through the Jarvis provider boundary.",
        "required_permission": "home_assistant.access",
        "risk_level": "low",
    },
    {
        "id": "retry_provider_writes",
        "title": "Retry deferred provider writes",
        "description": "Retry deferred calendar and inbox provider write-backs through the Jarvis boundary.",
        "required_permission": "home_assistant.access",
        "risk_level": "low",
    },
)


class HomeAssistantService:
    def __init__(self, *, store, client, user_store, membership_store, permission_store, resolve_effective_permissions, normalize_role, audit_log=None) -> None:
        self.store = store
        self.client = client
        self.user_store = user_store
        self.membership_store = membership_store
        self.permission_store = permission_store
        self.resolve_effective_permissions = resolve_effective_permissions
        self.normalize_role = normalize_role
        self.audit_log = audit_log
        self.confirmation_ttl_sec = int((os.getenv("JARVIS_HOME_ASSISTANT_CONFIRMATION_TTL_SEC") or "300").strip() or "300")
        self.remote_allowed_cidrs = tuple(
            item.strip()
            for item in (os.getenv("JARVIS_HOME_ASSISTANT_REMOTE_ALLOWED_CIDRS") or "").split(",")
            if item.strip()
        )

    def _write_audit(self, event: str, *, actor_user_id: str | None, actor_role: str | None, payload: dict | None = None) -> None:
        if not self.audit_log:
            return
        body = {
            "actor_user_id": actor_user_id,
            "actor_role": self.normalize_role(actor_role),
            **(payload or {}),
        }
        try:
            self.audit_log.write(event, body)
        except Exception:
            return

    def first_admin_user_id(self) -> str | None:
        for user in self.user_store.list_users():
            if user.get("role") == "admin":
                return user.get("id")
        return None

    def policy_snapshot(self, *, user_id: str | None, role: str | None) -> dict[str, object]:
        normalized_role = self.normalize_role(role)
        effective = sorted(self.resolve_effective_permissions(normalized_role, user_id, self.membership_store, self.permission_store))
        first_admin_user_id = self.first_admin_user_id()

        access_granted = False
        access_reason = "missing_explicit_capability"
        if user_id and first_admin_user_id and user_id == first_admin_user_id:
            access_granted = True
            access_reason = "first_global_admin"
        elif "home_assistant.access" in set(effective):
            access_granted = True
            access_reason = "explicit_permission"

        return {
            "first_admin_user_id": first_admin_user_id,
            "role": normalized_role,
            "effective_permissions": effective,
            "access_granted": access_granted,
            "access_reason": access_reason,
            "capability_groups": HOME_ASSISTANT_PERMISSION_GROUPS,
            "action_policies": {
                key: {
                    "capability": value.capability,
                    "risk_level": value.risk_level,
                    "requires_confirmation": value.requires_confirmation,
                    "remote_restricted": value.remote_restricted,
                }
                for key, value in HOME_ASSISTANT_ACTION_POLICIES.items()
            },
        }

    def require_access(self, *, user_id: str | None, role: str | None, required_permission: str | None = None) -> dict[str, object]:
        policy = self.policy_snapshot(user_id=user_id, role=role)
        effective = set(policy["effective_permissions"])
        if not policy["access_granted"]:
            raise HomeAssistantAccessError("home assistant access requires explicit permission")
        if required_permission and required_permission not in effective and policy["access_reason"] != "first_global_admin":
            raise HomeAssistantAccessError(f"missing permission: {required_permission}")
        return policy

    def _security_sensitive_entity(self, entity: dict[str, object], action: str) -> bool:
        kind = str(entity.get("kind") or "").strip().lower()
        security_kinds = {"alarm", "camera", "lock", "garage_door", "security", "doorbell"}
        security_actions = {"arm", "disarm", "lock", "unlock", "open", "close", "record", "stream"}
        return kind in security_kinds or action in security_actions

    def _action_policy_for_entity(self, entity: dict[str, object], action: str, remote: bool) -> dict[str, object]:
        is_security = self._security_sensitive_entity(entity, action)
        key = "device.control.security" if is_security else "device.control.basic"
        policy = HOME_ASSISTANT_ACTION_POLICIES[key]
        requires_confirmation = bool(policy.requires_confirmation or remote)
        return {
            "name": key,
            "capability": policy.capability,
            "risk_level": policy.risk_level,
            "requires_confirmation": requires_confirmation,
            "remote_restricted": bool(policy.remote_restricted or remote),
        }

    def _area_summary(self, entities: list[dict[str, object]]) -> list[dict[str, object]]:
        buckets: dict[str, dict[str, object]] = {}
        for item in entities:
            area = str(item.get("area") or "unassigned").strip() or "unassigned"
            bucket = buckets.setdefault(
                area,
                {"area": area, "entity_count": 0, "unavailable_count": 0, "kinds": set()},
            )
            bucket["entity_count"] += 1
            if item.get("available") is False:
                bucket["unavailable_count"] += 1
            kind = str(item.get("kind") or "").strip()
            if kind:
                bucket["kinds"].add(kind)
        ordered = []
        for area, item in sorted(buckets.items()):
            ordered.append(
                {
                    "area": area,
                    "entity_count": item["entity_count"],
                    "unavailable_count": item["unavailable_count"],
                    "kinds": sorted(item["kinds"]),
                }
            )
        return ordered

    def _apply_entity_action(self, entity: dict[str, object], action: str, value: object, actor_user_id: str | None) -> dict[str, object]:
        metadata = dict(entity.get("metadata") or {})
        metadata.update(
            {
                "last_action": action,
                "last_action_value": value,
                "last_actor_user_id": actor_user_id,
                "last_action_at": int(time.time()),
            }
        )
        state = str(value if value is not None else action)
        return self.store.update_managed_entity(
            entity["entity_id"],
            {
                "state": state,
                "metadata": metadata,
            },
        )

    def _apply_entity_sync(self, entity: dict[str, object], snapshot: dict[str, object] | None) -> dict[str, object]:
        if not snapshot:
            return entity
        metadata = dict(entity.get("metadata") or {})
        metadata.update(
            {
                "ha_attributes": snapshot.get("attributes") or {},
                "sync_source": "home_assistant",
                "last_synced_at": int(time.time()),
            }
        )
        return self.store.update_managed_entity(
            entity["entity_id"],
            {
                "state": snapshot.get("state"),
                "available": snapshot.get("state") not in {None, "unavailable", "unknown"},
                "metadata": metadata,
            },
        )

    def _request_is_expired(self, request: dict[str, object]) -> bool:
        created_at = int(request.get("created_at") or 0)
        if not created_at:
            return False
        return (int(time.time()) - created_at) > self.confirmation_ttl_sec

    def _materialize_request_status(self, request: dict[str, object]) -> dict[str, object]:
        if request.get("status") == "pending_confirmation" and self._request_is_expired(request):
            updated = self.store.update_control_request(
                str(request.get("id") or ""),
                {
                    "status": "expired",
                    "expired_at": int(time.time()),
                },
            )
            return updated or {**request, "status": "expired", "expired_at": int(time.time())}
        return request

    def security_posture(self, *, user_id: str | None, role: str | None) -> dict[str, object]:
        policy = self.require_access(user_id=user_id, role=role)
        requests = [self._materialize_request_status(item) for item in self.store.list_control_requests()]
        return {
            "policy": policy,
            "security": {
                "confirmation_ttl_sec": self.confirmation_ttl_sec,
                "remote_control_requires_capability": True,
                "system_control_preapproved_only": True,
                "remote_allowed_cidrs": list(self.remote_allowed_cidrs),
                "pending_confirmations": len([item for item in requests if item.get("status") == "pending_confirmation"]),
                "expired_confirmations": len([item for item in requests if item.get("status") == "expired"]),
            },
        }

    def _remote_client_allowed(self, client_ip: str | None) -> bool:
        if not self.remote_allowed_cidrs:
            return True
        if not client_ip:
            return False
        try:
            parsed_ip = ip_address(client_ip)
        except ValueError:
            return False
        for cidr in self.remote_allowed_cidrs:
            try:
                if parsed_ip in ip_network(cidr, strict=False):
                    return True
            except ValueError:
                continue
        return False

    def _provider_write_status_counts(self) -> dict[str, int]:
        deferred = 0
        synced = 0
        for item in [*self.store.list_calendar_items(), *self.store.list_inbox_items()]:
            status = str((item.get("metadata") or {}).get("provider_write") or "").strip().lower()
            if status == "deferred":
                deferred += 1
            elif status == "synced":
                synced += 1
        return {"deferred": deferred, "synced": synced}

    def _retry_calendar_provider_write(self, item: dict[str, object]) -> bool:
        metadata = dict(item.get("metadata") or {})
        operation = str(metadata.get("provider_operation") or "create").strip().lower()
        action = str(metadata.get("provider_last_action") or "").strip().lower()
        response = (
            self.client.update_calendar_item(item, action or "update")
            if operation == "update"
            else self.client.create_calendar_item(item)
        )
        if response is None:
            return False
        self.store.update_calendar_item(
            str(item.get("id") or ""),
            {
                "metadata": {
                    **metadata,
                    "provider_write": "synced",
                    "provider_response": response,
                }
            },
        )
        return True

    def _retry_inbox_provider_write(self, item: dict[str, object]) -> bool:
        metadata = dict(item.get("metadata") or {})
        operation = str(metadata.get("provider_operation") or "create").strip().lower()
        action = str(metadata.get("provider_last_action") or "").strip().lower()
        response = (
            self.client.update_inbox_item(item, action or "update")
            if operation == "update"
            else self.client.create_inbox_item(item)
        )
        if response is None:
            return False
        self.store.update_inbox_item(
            str(item.get("id") or ""),
            {
                "metadata": {
                    **metadata,
                    "provider_write": "synced",
                    "provider_response": response,
                }
            },
        )
        return True

    def _retry_deferred_provider_writes(self) -> dict[str, object]:
        calendar_retried = 0
        inbox_retried = 0
        for item in self.store.list_calendar_items():
            if str((item.get("metadata") or {}).get("provider_write") or "").strip().lower() != "deferred":
                continue
            if self._retry_calendar_provider_write(item):
                calendar_retried += 1
        for item in self.store.list_inbox_items():
            if str((item.get("metadata") or {}).get("provider_write") or "").strip().lower() != "deferred":
                continue
            if self._retry_inbox_provider_write(item):
                inbox_retried += 1
        return {
            "calendar_retried": calendar_retried,
            "inbox_retried": inbox_retried,
            "retried_total": calendar_retried + inbox_retried,
        }

    def overview(self, *, user_id: str | None, role: str | None) -> dict[str, object]:
        policy = self.require_access(user_id=user_id, role=role)
        entities = self.store.list_managed_entities()
        discovery = self.store.list_discovery_candidates()
        shopping_items = self.store.list_shopping_list_items()
        calendar_items = self.store.list_calendar_items()
        inbox_items = self.store.list_inbox_items()
        control_requests = self.store.list_control_requests()
        areas = sorted(
            {
                (item.get("area") or item.get("suggested_area") or "").strip()
                for item in [*entities, *discovery]
                if (item.get("area") or item.get("suggested_area") or "").strip()
            }
        )
        alerts = []
        if not self.client.config_summary().get("configured"):
            alerts.append({"level": "warning", "code": "ha_not_configured", "message": "Home Assistant backend is not configured yet."})
        unavailable = [item for item in entities if item.get("available") is False]
        if unavailable:
            alerts.append({"level": "warning", "code": "entities_unavailable", "message": f"{len(unavailable)} managed entit(y/ies) currently unavailable."})
        pending = [item for item in control_requests if item.get("status") == "pending_confirmation"]
        if pending:
            alerts.append({"level": "info", "code": "pending_confirmations", "message": f"{len(pending)} control request(s) waiting for confirmation."})
        provider_write_counts = self._provider_write_status_counts()
        if provider_write_counts["deferred"]:
            alerts.append(
                {
                    "level": "warning",
                    "code": "provider_write_deferred",
                    "message": f"{provider_write_counts['deferred']} provider write(s) are deferred and can be retried from recovery playbooks.",
                }
            )
        return {
            "policy": policy,
            "integration": self.client.config_summary(),
            "security": self.security_posture(user_id=user_id, role=role)["security"],
            "store": self.store.get_config(),
            "counts": {
                "managed_entities": len(entities),
                "discovery_candidates": len(discovery),
                "shopping_list_items": len(shopping_items),
                "calendar_items": len(calendar_items),
                "inbox_items": len(inbox_items),
                "system_targets": len(self.store.list_system_targets()),
                "control_requests": len(control_requests),
                "deferred_provider_writes": provider_write_counts["deferred"],
            },
            "areas": areas,
            "shopping_lists": [{"id": "default", "name": "Shopping list", "open_items": len([item for item in shopping_items if item.get("status") != "done"])}],
            "calendar_items": calendar_items,
            "inbox_items": inbox_items,
            "alerts": alerts,
        }

    def device_profiles(self, *, user_id: str | None, role: str | None) -> dict[str, object]:
        policy = self.require_access(user_id=user_id, role=role)
        return {"policy": policy, "profiles": DEVICE_ACTION_PROFILES}

    def system_target_profiles(self, *, user_id: str | None, role: str | None) -> dict[str, object]:
        policy = self.require_access(user_id=user_id, role=role)
        return {"policy": policy, "profiles": SYSTEM_TARGET_PROFILES}

    def area_summary(self, *, user_id: str | None, role: str | None) -> dict[str, object]:
        policy = self.require_access(user_id=user_id, role=role)
        entities = self.store.list_managed_entities()
        return {"policy": policy, "areas": self._area_summary(entities)}

    def list_system_targets(self, *, user_id: str | None, role: str | None) -> dict[str, object]:
        policy = self.require_access(user_id=user_id, role=role)
        return {"policy": policy, "targets": self.store.list_system_targets()}

    def create_system_target(self, payload: dict[str, object], *, user_id: str | None, role: str | None) -> dict[str, object]:
        policy = self.require_access(user_id=user_id, role=role, required_permission="home_assistant.integration_management")
        label = str((payload or {}).get("label") or "").strip()
        target_kind = str((payload or {}).get("target_kind") or "pc").strip().lower()
        if not label:
            raise ValueError("system target label required")
        if target_kind not in SYSTEM_TARGET_PROFILES:
            raise ValueError("unsupported system target kind")
        target = self.store.add_system_target(
            {
                "id": payload.get("id") or f"sys-{uuid.uuid4().hex[:12]}",
                "label": label,
                "target_kind": target_kind,
                "host": str((payload or {}).get("host") or "").strip(),
                "area": str((payload or {}).get("area") or "").strip(),
                "allowed_actions": (payload or {}).get("allowed_actions") or [item["action"] for item in SYSTEM_TARGET_PROFILES[target_kind]["actions"]],
                "status": str((payload or {}).get("status") or "ready").strip(),
                "risk_level": str((payload or {}).get("risk_level") or "high").strip(),
                "integration_source": str((payload or {}).get("integration_source") or "jarvis_preapproved").strip(),
                "metadata": (payload or {}).get("metadata") or {},
                "created_at": int(time.time()),
                "created_by": user_id,
            }
        )
        self._write_audit(
            "ha_system_target_created",
            actor_user_id=user_id,
            actor_role=role,
            payload={"target_id": target["id"], "target_kind": target["target_kind"], "label": target["label"]},
        )
        return {"policy": policy, "target": target}

    def list_discovery_candidates(self, *, user_id: str | None, role: str | None) -> dict[str, object]:
        policy = self.require_access(user_id=user_id, role=role, required_permission="home_assistant.device_discovery")
        return {"policy": policy, "candidates": self.store.list_discovery_candidates()}

    def create_discovery_candidate(self, payload: dict[str, object], *, user_id: str | None, role: str | None) -> dict[str, object]:
        policy = self.require_access(user_id=user_id, role=role, required_permission="home_assistant.device_discovery")
        candidate = {
            "id": payload.get("id") or f"hac-{uuid.uuid4().hex[:12]}",
            "source": payload.get("source") or "manual",
            "ip_address": payload.get("ip_address") or "",
            "label": payload.get("label") or "",
            "suggested_type": payload.get("suggested_type") or "unknown",
            "suggested_area": payload.get("suggested_area") or "",
            "trust_level": payload.get("trust_level") or "untrusted",
            "risk_level": payload.get("risk_level") or "medium",
            "onboarding_status": payload.get("onboarding_status") or "review_pending",
            "approval_status": payload.get("approval_status") or "pending",
            "created_at": payload.get("created_at") or int(time.time()),
            "metadata": payload.get("metadata") or {},
        }
        item = self.store.add_discovery_candidate(candidate)
        self._write_audit(
            "ha_discovery_candidate_created",
            actor_user_id=user_id,
            actor_role=role,
            payload={"candidate_id": item["id"], "label": item.get("label"), "suggested_type": item.get("suggested_type")},
        )
        return {"policy": policy, "candidate": item}

    def list_managed_entities(self, *, user_id: str | None, role: str | None) -> dict[str, object]:
        policy = self.require_access(user_id=user_id, role=role)
        return {"policy": policy, "entities": self.store.list_managed_entities()}

    def _sync_managed_entities_snapshot(self) -> tuple[list[dict[str, object]], int]:
        managed_entities = self.store.list_managed_entities()
        snapshots = {item.get("entity_id"): item for item in self.client.fetch_states()}
        updated = []
        synced = 0
        for entity in managed_entities:
            snapshot = snapshots.get(entity.get("entity_id"))
            if snapshot:
                updated_entity = self._apply_entity_sync(entity, snapshot)
                updated.append(updated_entity or entity)
                synced += 1
            else:
                updated.append(entity)
        return updated, synced

    def sync_managed_entities(self, *, user_id: str | None, role: str | None) -> dict[str, object]:
        policy = self.require_access(user_id=user_id, role=role)
        updated, synced = self._sync_managed_entities_snapshot()
        result = {
            "policy": policy,
            "entities": updated,
            "sync": {
                "configured": self.client.config_summary().get("configured", False),
                "synced_count": synced,
                "total_entities": len(updated),
                "timestamp": int(time.time()),
            },
        }
        self._write_audit(
            "ha_entities_synced",
            actor_user_id=user_id,
            actor_role=role,
            payload={"synced_count": synced, "total_entities": len(updated)},
        )
        return result

    def live_snapshot(self, *, user_id: str | None, role: str | None) -> dict[str, object]:
        policy = self.require_access(user_id=user_id, role=role)
        entities, synced = self._sync_managed_entities_snapshot()
        automations = self.store.list_automation_rules()
        return {
            "policy": policy,
            "integration": self.client.config_summary(),
            "areas": self._area_summary(entities),
            "entities": entities,
            "automations": automations,
            "sync": {
                "configured": self.client.config_summary().get("configured", False),
                "synced_count": synced,
                "total_entities": len(entities),
                "timestamp": int(time.time()),
            },
        }

    def list_control_requests(self, *, user_id: str | None, role: str | None) -> dict[str, object]:
        policy = self.require_access(user_id=user_id, role=role)
        return {"policy": policy, "requests": [self._materialize_request_status(item) for item in self.store.list_control_requests()]}

    def health_status(self, *, user_id: str | None, role: str | None) -> dict[str, object]:
        policy = self.require_access(user_id=user_id, role=role)
        entities = self.store.list_managed_entities()
        requests = [self._materialize_request_status(item) for item in self.store.list_control_requests()]
        automations = self.store.list_automation_rules()
        unavailable = [item for item in entities if item.get("available") is False]
        pending = [item for item in requests if item.get("status") == "pending_confirmation"]
        provider_write_counts = self._provider_write_status_counts()
        return {
            "policy": policy,
            "integration": self.client.config_summary(),
            "health": {
                "managed_entities": len(entities),
                "unavailable_entities": len(unavailable),
                "pending_confirmations": len(pending),
                "automation_rules": len(automations),
                "deferred_provider_writes": provider_write_counts["deferred"],
                "configured": self.client.config_summary().get("configured", False),
            },
            "alerts": {
                "unavailable_entities": unavailable,
                "pending_requests": pending,
            },
        }

    def list_recovery_playbooks(self, *, user_id: str | None, role: str | None) -> dict[str, object]:
        policy = self.require_access(user_id=user_id, role=role)
        effective = set(policy["effective_permissions"])
        if policy["access_reason"] == "first_global_admin":
            items = list(RECOVERY_PLAYBOOKS)
        else:
            items = [item for item in RECOVERY_PLAYBOOKS if item["required_permission"] in effective]
        return {"policy": policy, "playbooks": items}

    def execute_recovery_playbook(self, playbook_id: str, *, user_id: str | None, role: str | None) -> dict[str, object]:
        playbook = next((item for item in RECOVERY_PLAYBOOKS if item["id"] == playbook_id), None)
        if not playbook:
            raise LookupError("recovery playbook not found")

        policy = self.require_access(user_id=user_id, role=role, required_permission=str(playbook["required_permission"]))
        result: dict[str, object]
        if playbook_id == "sync_entities":
            result = self.sync_managed_entities(user_id=user_id, role=role)
        elif playbook_id == "review_pending_confirmations":
            result = self.list_control_requests(user_id=user_id, role=role)
        elif playbook_id == "disable_automations":
            changed = []
            for rule in self.store.list_automation_rules():
                if rule.get("enabled"):
                    updated = self.store.update_automation_rule(
                        rule["id"],
                        {
                            "enabled": False,
                            "updated_at": int(time.time()),
                            "updated_by": user_id,
                        },
                    )
                    if updated:
                        changed.append(updated)
            result = {"automations": changed, "disabled_count": len(changed)}
        elif playbook_id == "sync_personal_assistant_data":
            result = {
                "calendar_sync": self.sync_calendar_items(user_id=user_id, role=role),
                "inbox_sync": self.sync_inbox_items(user_id=user_id, role=role),
            }
        elif playbook_id == "retry_provider_writes":
            result = self._retry_deferred_provider_writes()
        else:
            result = {}

        response = {
            "policy": policy,
            "playbook": playbook,
            "result": result,
            "executed_at": int(time.time()),
        }
        self._write_audit(
            "ha_recovery_playbook_executed",
            actor_user_id=user_id,
            actor_role=role,
            payload={"playbook_id": playbook_id},
        )
        return response

    def list_automation_rules(self, *, user_id: str | None, role: str | None) -> dict[str, object]:
        policy = self.require_access(user_id=user_id, role=role)
        return {"policy": policy, "automations": self.store.list_automation_rules()}

    def create_automation_rule(self, payload: dict[str, object], *, user_id: str | None, role: str | None) -> dict[str, object]:
        policy = self.require_access(user_id=user_id, role=role, required_permission="home_assistant.automation_management")
        name = str((payload or {}).get("name") or "").strip()
        if not name:
            raise ValueError("automation name required")
        rule = self.store.add_automation_rule(
            {
                "id": payload.get("id") or f"ha-auto-{uuid.uuid4().hex[:12]}",
                "name": name,
                "description": str((payload or {}).get("description") or "").strip(),
                "trigger": str((payload or {}).get("trigger") or "manual").strip(),
                "target_area": str((payload or {}).get("target_area") or "").strip(),
                "action_summary": str((payload or {}).get("action_summary") or "").strip(),
                "enabled": bool((payload or {}).get("enabled", True)),
                "review_state": str((payload or {}).get("review_state") or "approved").strip(),
                "risk_level": str((payload or {}).get("risk_level") or "medium").strip(),
                "created_at": int(time.time()),
                "updated_at": int(time.time()),
                "created_by": user_id,
                "metadata": (payload or {}).get("metadata") or {},
            }
        )
        self._write_audit(
            "ha_automation_created",
            actor_user_id=user_id,
            actor_role=role,
            payload={"automation_id": rule["id"], "name": rule["name"], "risk_level": rule["risk_level"]},
        )
        return {"policy": policy, "automation": rule}

    def toggle_automation_rule(self, rule_id: str, payload: dict[str, object] | None, *, user_id: str | None, role: str | None) -> dict[str, object]:
        policy = self.require_access(user_id=user_id, role=role, required_permission="home_assistant.automation_management")
        rule = self.store.get_automation_rule(rule_id)
        if not rule:
            raise LookupError("automation rule not found")
        enabled = bool((payload or {}).get("enabled", not bool(rule.get("enabled", True))))
        updated = self.store.update_automation_rule(
            rule_id,
            {
                "enabled": enabled,
                "updated_at": int(time.time()),
                "updated_by": user_id,
            },
        )
        self._write_audit(
            "ha_automation_toggled",
            actor_user_id=user_id,
            actor_role=role,
            payload={"automation_id": rule_id, "enabled": enabled},
        )
        return {"policy": policy, "automation": updated}

    def approve_discovery_candidate(
        self,
        candidate_id: str,
        payload: dict[str, object] | None,
        *,
        user_id: str | None,
        role: str | None,
    ) -> dict[str, object]:
        policy = self.require_access(user_id=user_id, role=role, required_permission="home_assistant.integration_management")
        candidate = self.store.get_discovery_candidate(candidate_id)
        if not candidate:
            raise LookupError("discovery candidate not found")
        updated_candidate = self.store.update_discovery_candidate(
            candidate_id,
            {
                "approval_status": "approved",
                "onboarding_status": "approved_for_integration",
                "approved_at": int(time.time()),
            },
        )
        entity = self.store.add_managed_entity(
            {
                "source_candidate_id": candidate_id,
                "entity_id": (payload or {}).get("entity_id") or f"entity.{candidate.get('suggested_type')}.{candidate_id.replace('-', '_')}",
                "label": (payload or {}).get("label") or candidate.get("label"),
                "kind": (payload or {}).get("kind") or candidate.get("suggested_type"),
                "area": (payload or {}).get("area") or candidate.get("suggested_area"),
                "integration_source": "home_assistant",
                "control_mode": "approval_required",
                "trust_level": candidate.get("trust_level") or "untrusted",
                "risk_level": candidate.get("risk_level") or "medium",
                "approval_status": "approved",
                "onboarding_status": "managed",
                "created_at": int(time.time()),
                "metadata": candidate.get("metadata") or {},
            }
        )
        self._write_audit(
            "ha_discovery_candidate_approved",
            actor_user_id=user_id,
            actor_role=role,
            payload={"candidate_id": candidate_id, "entity_id": entity["entity_id"], "kind": entity["kind"]},
        )
        return {"policy": policy, "candidate": updated_candidate, "entity": entity}

    def list_shopping_list_items(self, *, user_id: str | None, role: str | None) -> dict[str, object]:
        policy = self.require_access(user_id=user_id, role=role)
        return {"policy": policy, "items": self.store.list_shopping_list_items()}

    def add_shopping_list_item(self, payload: dict[str, object], *, user_id: str | None, role: str | None) -> dict[str, object]:
        policy = self.require_access(user_id=user_id, role=role)
        title = str((payload or {}).get("title") or "").strip()
        if not title:
            raise ValueError("shopping list item title required")
        item = self.store.add_shopping_list_item(
            {
                "id": payload.get("id") or f"shop-{uuid.uuid4().hex[:12]}",
                "title": title,
                "list_id": (payload or {}).get("list_id") or "default",
                "status": (payload or {}).get("status") or "open",
                "source": (payload or {}).get("source") or "jarvis",
                "created_at": int(time.time()),
                "metadata": (payload or {}).get("metadata") or {},
            }
        )
        self._write_audit(
            "ha_shopping_item_added",
            actor_user_id=user_id,
            actor_role=role,
            payload={"item_id": item["id"], "title": item["title"]},
        )
        return {"policy": policy, "item": item}

    def list_calendar_items(self, *, user_id: str | None, role: str | None) -> dict[str, object]:
        policy = self.require_access(user_id=user_id, role=role)
        return {"policy": policy, "items": self.store.list_calendar_items()}

    def sync_calendar_items(self, *, user_id: str | None, role: str | None) -> dict[str, object]:
        policy = self.require_access(user_id=user_id, role=role)
        source_items = self.client.fetch_calendar_items()
        synced_items = self.store.replace_calendar_items(
            [
                {
                    "id": item.get("id") or f"cal-sync-{uuid.uuid4().hex[:12]}",
                    "title": str(item.get("title") or "").strip(),
                    "starts_at": str(item.get("starts_at") or "").strip(),
                    "ends_at": str(item.get("ends_at") or "").strip(),
                    "calendar_id": str(item.get("calendar_id") or "default").strip(),
                    "status": str(item.get("status") or "scheduled").strip(),
                    "source": str(item.get("source") or "provider").strip(),
                    "created_at": int(item.get("created_at") or time.time()),
                    "metadata": item.get("metadata") or {},
                }
                for item in source_items
                if str(item.get("title") or "").strip() and str(item.get("starts_at") or "").strip()
            ]
        )
        result = {
            "policy": policy,
            "items": synced_items,
            "sync": {
                "provider": self.client.config_summary().get("calendar_provider", "scaffold"),
                "synced_count": len(synced_items),
                "timestamp": int(time.time()),
            },
        }
        self._write_audit(
            "ha_calendar_synced",
            actor_user_id=user_id,
            actor_role=role,
            payload={"provider": result["sync"]["provider"], "synced_count": len(synced_items)},
        )
        return result

    def add_calendar_item(self, payload: dict[str, object], *, user_id: str | None, role: str | None) -> dict[str, object]:
        policy = self.require_access(user_id=user_id, role=role)
        title = str((payload or {}).get("title") or "").strip()
        if not title:
            raise ValueError("calendar item title required")
        starts_at = str((payload or {}).get("starts_at") or "").strip()
        if not starts_at:
            raise ValueError("calendar item starts_at required")
        item = self.store.add_calendar_item(
            {
                "id": payload.get("id") or f"cal-{uuid.uuid4().hex[:12]}",
                "title": title,
                "starts_at": starts_at,
                "ends_at": str((payload or {}).get("ends_at") or "").strip(),
                "calendar_id": str((payload or {}).get("calendar_id") or "default").strip(),
                "status": str((payload or {}).get("status") or "scheduled").strip(),
                "source": str((payload or {}).get("source") or "jarvis").strip(),
                "created_at": int(time.time()),
                "metadata": {
                    **((payload or {}).get("metadata") or {}),
                    "provider_write": "local_only",
                    "provider_operation": "create",
                },
            }
        )
        provider_response = self.client.create_calendar_item(item)
        if self.client.config_summary().get("calendar_write_enabled"):
            if provider_response is not None:
                item = self.store.update_calendar_item(
                    item["id"],
                    {
                        "metadata": {
                            **(item.get("metadata") or {}),
                            "provider_write": "synced",
                            "provider_response": provider_response,
                        }
                    },
                ) or item
                self._write_audit(
                    "ha_calendar_provider_write_synced",
                    actor_user_id=user_id,
                    actor_role=role,
                    payload={"item_id": item["id"]},
                )
            else:
                item = self.store.update_calendar_item(
                    item["id"],
                    {
                        "metadata": {
                            **(item.get("metadata") or {}),
                            "provider_write": "deferred",
                        }
                    },
                ) or item
                self._write_audit(
                    "ha_calendar_provider_write_deferred",
                    actor_user_id=user_id,
                    actor_role=role,
                    payload={"item_id": item["id"]},
                )
        self._write_audit(
            "ha_calendar_item_added",
            actor_user_id=user_id,
            actor_role=role,
            payload={"item_id": item["id"], "title": item["title"], "starts_at": item["starts_at"]},
        )
        return {"policy": policy, "item": item}

    def act_on_calendar_item(self, item_id: str, payload: dict[str, object] | None, *, user_id: str | None, role: str | None) -> dict[str, object]:
        policy = self.require_access(user_id=user_id, role=role)
        item = self.store.get_calendar_item(item_id)
        if not item:
            raise LookupError("calendar item not found")
        action = str((payload or {}).get("action") or "").strip().lower()
        if action not in {"mark_done", "reschedule_plus_1d"}:
            raise ValueError("unsupported calendar action")

        patch: dict[str, object]
        if action == "mark_done":
            patch = {
                "status": "completed",
                "metadata": {
                    **(item.get("metadata") or {}),
                    "last_action": action,
                    "last_actor_user_id": user_id,
                    "last_action_at": int(time.time()),
                },
            }
        else:
            starts_at = str(item.get("starts_at") or "").strip()
            patch = {
                "status": "rescheduled",
                "starts_at": f"{starts_at} +1d" if starts_at else "+1d",
                "metadata": {
                    **(item.get("metadata") or {}),
                    "last_action": action,
                    "last_actor_user_id": user_id,
                    "last_action_at": int(time.time()),
                },
            }
        updated = self.store.update_calendar_item(item_id, patch)
        if self.client.config_summary().get("calendar_write_enabled") and updated:
            provider_response = self.client.update_calendar_item(updated, action)
            metadata = {
                **(updated.get("metadata") or {}),
                "provider_write": "synced" if provider_response is not None else "deferred",
                "provider_operation": "update",
                "provider_last_action": action,
            }
            if provider_response is not None:
                metadata["provider_response"] = provider_response
                self._write_audit(
                    "ha_calendar_provider_action_synced",
                    actor_user_id=user_id,
                    actor_role=role,
                    payload={"item_id": item_id, "action": action},
                )
            else:
                self._write_audit(
                    "ha_calendar_provider_action_deferred",
                    actor_user_id=user_id,
                    actor_role=role,
                    payload={"item_id": item_id, "action": action},
                )
            updated = self.store.update_calendar_item(item_id, {"metadata": metadata}) or updated
        self._write_audit(
            "ha_calendar_item_updated",
            actor_user_id=user_id,
            actor_role=role,
            payload={"item_id": item_id, "action": action, "status": updated.get("status") if updated else None},
        )
        return {"policy": policy, "item": updated}

    def list_inbox_items(self, *, user_id: str | None, role: str | None) -> dict[str, object]:
        policy = self.require_access(user_id=user_id, role=role)
        return {"policy": policy, "items": self.store.list_inbox_items()}

    def sync_inbox_items(self, *, user_id: str | None, role: str | None) -> dict[str, object]:
        policy = self.require_access(user_id=user_id, role=role)
        source_items = self.client.fetch_inbox_items()
        synced_items = self.store.replace_inbox_items(
            [
                {
                    "id": item.get("id") or f"inbox-sync-{uuid.uuid4().hex[:12]}",
                    "subject": str(item.get("subject") or "").strip(),
                    "from_label": str(item.get("from_label") or "unknown").strip(),
                    "status": str(item.get("status") or "unread").strip(),
                    "received_at": int(item.get("received_at") or time.time()),
                    "source": str(item.get("source") or "provider").strip(),
                    "summary": str(item.get("summary") or "").strip(),
                    "metadata": item.get("metadata") or {},
                }
                for item in source_items
                if str(item.get("subject") or "").strip()
            ]
        )
        result = {
            "policy": policy,
            "items": synced_items,
            "sync": {
                "provider": self.client.config_summary().get("inbox_provider", "scaffold"),
                "synced_count": len(synced_items),
                "timestamp": int(time.time()),
            },
        }
        self._write_audit(
            "ha_inbox_synced",
            actor_user_id=user_id,
            actor_role=role,
            payload={"provider": result["sync"]["provider"], "synced_count": len(synced_items)},
        )
        return result

    def add_inbox_item(self, payload: dict[str, object], *, user_id: str | None, role: str | None) -> dict[str, object]:
        policy = self.require_access(user_id=user_id, role=role)
        subject = str((payload or {}).get("subject") or "").strip()
        if not subject:
            raise ValueError("inbox item subject required")
        item = self.store.add_inbox_item(
            {
                "id": payload.get("id") or f"inbox-{uuid.uuid4().hex[:12]}",
                "subject": subject,
                "from_label": str((payload or {}).get("from_label") or "unknown").strip(),
                "status": str((payload or {}).get("status") or "unread").strip(),
                "received_at": int((payload or {}).get("received_at") or time.time()),
                "source": str((payload or {}).get("source") or "jarvis").strip(),
                "summary": str((payload or {}).get("summary") or "").strip(),
                "metadata": {
                    **((payload or {}).get("metadata") or {}),
                    "provider_write": "local_only",
                    "provider_operation": "create",
                },
            }
        )
        provider_response = self.client.create_inbox_item(item)
        if self.client.config_summary().get("inbox_write_enabled"):
            if provider_response is not None:
                item = self.store.update_inbox_item(
                    item["id"],
                    {
                        "metadata": {
                            **(item.get("metadata") or {}),
                            "provider_write": "synced",
                            "provider_response": provider_response,
                        }
                    },
                ) or item
                self._write_audit(
                    "ha_inbox_provider_write_synced",
                    actor_user_id=user_id,
                    actor_role=role,
                    payload={"item_id": item["id"]},
                )
            else:
                item = self.store.update_inbox_item(
                    item["id"],
                    {
                        "metadata": {
                            **(item.get("metadata") or {}),
                            "provider_write": "deferred",
                        }
                    },
                ) or item
                self._write_audit(
                    "ha_inbox_provider_write_deferred",
                    actor_user_id=user_id,
                    actor_role=role,
                    payload={"item_id": item["id"]},
                )
        self._write_audit(
            "ha_inbox_item_added",
            actor_user_id=user_id,
            actor_role=role,
            payload={"item_id": item["id"], "subject": item["subject"], "from_label": item["from_label"]},
        )
        return {"policy": policy, "item": item}

    def act_on_inbox_item(self, item_id: str, payload: dict[str, object] | None, *, user_id: str | None, role: str | None) -> dict[str, object]:
        policy = self.require_access(user_id=user_id, role=role)
        item = self.store.get_inbox_item(item_id)
        if not item:
            raise LookupError("inbox item not found")
        action = str((payload or {}).get("action") or "").strip().lower()
        if action not in {"mark_read", "archive"}:
            raise ValueError("unsupported inbox action")

        next_status = "read" if action == "mark_read" else "archived"
        updated = self.store.update_inbox_item(
            item_id,
            {
                "status": next_status,
                "metadata": {
                    **(item.get("metadata") or {}),
                    "last_action": action,
                    "last_actor_user_id": user_id,
                    "last_action_at": int(time.time()),
                },
            },
        )
        if self.client.config_summary().get("inbox_write_enabled") and updated:
            provider_response = self.client.update_inbox_item(updated, action)
            metadata = {
                **(updated.get("metadata") or {}),
                "provider_write": "synced" if provider_response is not None else "deferred",
                "provider_operation": "update",
                "provider_last_action": action,
            }
            if provider_response is not None:
                metadata["provider_response"] = provider_response
                self._write_audit(
                    "ha_inbox_provider_action_synced",
                    actor_user_id=user_id,
                    actor_role=role,
                    payload={"item_id": item_id, "action": action},
                )
            else:
                self._write_audit(
                    "ha_inbox_provider_action_deferred",
                    actor_user_id=user_id,
                    actor_role=role,
                    payload={"item_id": item_id, "action": action},
                )
            updated = self.store.update_inbox_item(item_id, {"metadata": metadata}) or updated
        self._write_audit(
            "ha_inbox_item_updated",
            actor_user_id=user_id,
            actor_role=role,
            payload={"item_id": item_id, "action": action, "status": updated.get("status") if updated else None},
        )
        return {"policy": policy, "item": updated}

    def request_entity_action(self, entity_id: str, payload: dict[str, object], *, user_id: str | None, role: str | None, client_ip: str | None = None) -> dict[str, object]:
        entity = self.store.get_managed_entity(entity_id)
        if not entity:
            raise LookupError("managed entity not found")

        action = str((payload or {}).get("action") or "").strip().lower()
        if not action:
            raise ValueError("entity action required")
        value = (payload or {}).get("value")
        remote = bool((payload or {}).get("remote", False))
        action_policy = self._action_policy_for_entity(entity, action, remote)
        if remote:
            self.require_access(user_id=user_id, role=role, required_permission="home_assistant.remote_control")
            if not self._remote_client_allowed(client_ip):
                raise HomeAssistantAccessError("remote action denied by network policy")
        policy = self.require_access(user_id=user_id, role=role, required_permission=action_policy["capability"])

        request = {
            "id": f"ha-req-{uuid.uuid4().hex[:12]}",
            "entity_id": entity_id,
            "entity_label": entity.get("label"),
            "action": action,
            "value": value,
            "risk_level": action_policy["risk_level"],
            "required_capability": action_policy["capability"],
            "requires_confirmation": action_policy["requires_confirmation"],
            "remote_restricted": action_policy["remote_restricted"],
            "status": "pending_confirmation" if action_policy["requires_confirmation"] else "executed",
            "requested_by": user_id,
            "created_at": int(time.time()),
        }
        stored_request = self.store.add_control_request(request)

        updated_entity = entity
        if not action_policy["requires_confirmation"]:
            updated_entity = self._apply_entity_action(entity, action, value, user_id)
            stored_request = self.store.update_control_request(
                request["id"],
                {
                    "status": "executed",
                    "executed_at": int(time.time()),
                },
            ) or stored_request

        result = {
            "policy": policy,
            "request": stored_request,
            "entity": updated_entity,
            "executed": not action_policy["requires_confirmation"],
        }
        self._write_audit(
            "ha_entity_action_requested" if action_policy["requires_confirmation"] else "ha_entity_action_executed",
            actor_user_id=user_id,
            actor_role=role,
            payload={"entity_id": entity_id, "action": action, "remote": remote, "request_id": stored_request["id"]},
        )
        return result

    def request_system_target_action(self, target_id: str, payload: dict[str, object], *, user_id: str | None, role: str | None, client_ip: str | None = None) -> dict[str, object]:
        target = self.store.get_system_target(target_id)
        if not target:
            raise LookupError("system target not found")
        action = str((payload or {}).get("action") or "").strip().lower()
        if not action:
            raise ValueError("system action required")
        allowed_actions = {str(item).strip().lower() for item in target.get("allowed_actions") or []}
        if action not in allowed_actions:
            raise ValueError("system action is not preapproved for this target")
        remote = bool((payload or {}).get("remote", False))
        if remote:
            self.require_access(user_id=user_id, role=role, required_permission="home_assistant.remote_control")
            if not self._remote_client_allowed(client_ip):
                raise HomeAssistantAccessError("remote action denied by network policy")
        policy = self.require_access(user_id=user_id, role=role, required_permission="home_assistant.system_control")
        action_policy = HOME_ASSISTANT_ACTION_POLICIES["system.control.preapproved"]
        request = self.store.add_control_request(
            {
                "id": f"ha-sys-{uuid.uuid4().hex[:12]}",
                "request_type": "system_target",
                "target_id": target_id,
                "entity_id": target_id,
                "entity_label": target.get("label"),
                "action": action,
                "value": (payload or {}).get("value"),
                "risk_level": action_policy.risk_level,
                "required_capability": action_policy.capability,
                "requires_confirmation": True,
                "remote_restricted": bool(action_policy.remote_restricted or remote),
                "status": "pending_confirmation",
                "requested_by": user_id,
                "created_at": int(time.time()),
                "metadata": {"target_kind": target.get("target_kind"), "remote": remote},
            }
        )
        self._write_audit(
            "ha_system_action_requested",
            actor_user_id=user_id,
            actor_role=role,
            payload={"target_id": target_id, "action": action, "remote": remote, "request_id": request["id"]},
        )
        return {"policy": policy, "request": request, "target": target, "executed": False}

    def confirm_control_request(self, request_id: str, payload: dict[str, object] | None, *, user_id: str | None, role: str | None) -> dict[str, object]:
        request = self.store.get_control_request(request_id)
        if not request:
            raise LookupError("control request not found")
        request = self._materialize_request_status(request)
        if request.get("status") != "pending_confirmation":
            if request.get("status") == "expired":
                raise ValueError("control request confirmation expired")
            raise ValueError("control request is not pending confirmation")

        policy = self.require_access(user_id=user_id, role=role, required_permission=str(request.get("required_capability") or "home_assistant.device_control"))
        if request.get("request_type") == "system_target":
            target = self.store.get_system_target(str(request.get("target_id") or ""))
            if not target:
                raise LookupError("system target not found")
            confirmed = bool((payload or {}).get("confirmed", True))
            if not confirmed:
                updated_request = self.store.update_control_request(
                    request_id,
                    {
                        "status": "denied",
                        "denied_at": int(time.time()),
                        "confirmed_by": user_id,
                    },
                )
                self._write_audit(
                    "ha_control_request_denied",
                    actor_user_id=user_id,
                    actor_role=role,
                    payload={"request_id": request_id, "request_type": "system_target"},
                )
                return {"policy": policy, "request": updated_request, "target": target, "executed": False}

            updated_target = self.store.update_system_target(
                str(target.get("id") or ""),
                {
                    "status": f"last_action:{request.get('action')}",
                    "last_action": request.get("action"),
                    "last_action_at": int(time.time()),
                    "last_actor_user_id": user_id,
                },
            ) or target
            updated_request = self.store.update_control_request(
                request_id,
                {
                    "status": "executed",
                    "confirmed_at": int(time.time()),
                    "confirmed_by": user_id,
                },
            )
            self._write_audit(
                "ha_system_action_confirmed",
                actor_user_id=user_id,
                actor_role=role,
                payload={"request_id": request_id, "target_id": target.get("id"), "action": request.get("action")},
            )
            return {"policy": policy, "request": updated_request, "target": updated_target, "executed": True}

        entity = self.store.get_managed_entity(str(request.get("entity_id") or ""))
        if not entity:
            raise LookupError("managed entity not found")

        confirmed = bool((payload or {}).get("confirmed", True))
        if not confirmed:
            updated_request = self.store.update_control_request(
                request_id,
                {
                    "status": "denied",
                    "denied_at": int(time.time()),
                    "confirmed_by": user_id,
                },
            )
            self._write_audit(
                "ha_control_request_denied",
                actor_user_id=user_id,
                actor_role=role,
                payload={"request_id": request_id, "request_type": "entity"},
            )
            return {"policy": policy, "request": updated_request, "entity": entity, "executed": False}

        updated_entity = self._apply_entity_action(entity, str(request.get("action") or ""), request.get("value"), user_id)
        updated_request = self.store.update_control_request(
            request_id,
            {
                "status": "executed",
                "confirmed_at": int(time.time()),
                "confirmed_by": user_id,
            },
        )
        self._write_audit(
            "ha_entity_action_confirmed",
            actor_user_id=user_id,
            actor_role=role,
            payload={"request_id": request_id, "entity_id": entity.get("entity_id"), "action": request.get("action")},
        )
        return {"policy": policy, "request": updated_request, "entity": updated_entity, "executed": True}
