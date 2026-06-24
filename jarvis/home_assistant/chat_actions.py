from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class HomeAssistantChatContext:
    service: object
    text: str
    cleaned: str
    normalized: str
    user_id: str | None
    role: str | None


Executor = Callable[[HomeAssistantChatContext, dict[str, object]], dict[str, object]]


@dataclass(frozen=True)
class HomeAssistantChatActionDefinition:
    name: str
    summary: str
    required_fields: tuple[str, ...]
    executor: Executor
    risk_level: str = "low"
    requires_confirmation: bool = False


def _humanize_entity_action(action: str) -> str:
    mapping = {
        "turn_on": "eingeschaltet",
        "turn_off": "ausgeschaltet",
        "lock": "verriegelt",
        "unlock": "entriegelt",
        "open": "geöffnet",
        "close": "geschlossen",
        "arm": "aktiviert",
        "disarm": "deaktiviert",
        "record": "zur Aufnahme aktiviert",
        "stream": "für Streaming angefragt",
        "set_brightness": "auf neue Helligkeit gesetzt",
        "set_temperature": "auf neue Temperatur gesetzt",
        "set_color_temp": "auf neue Farbtemperatur gesetzt",
        "set_hvac_mode": "auf neuen Modus gesetzt",
    }
    return mapping.get(action, action)


def _sync_entities(ctx: HomeAssistantChatContext, _params: dict[str, object]) -> dict[str, object]:
    result = ctx.service.sync_managed_entities(user_id=ctx.user_id, role=ctx.role)
    sync = result.get("sync") or {}
    return {
        "reply": f"Home-Assistant-Geräte synchronisiert: {sync.get('synced_count', 0)} von {sync.get('total_entities', 0)} Geräten aktualisiert.",
        "data": {"route": "home_assistant_chat", "intent": "sync_entities", "action": "sync_entities", "sync": sync},
    }


def _list_open_requests(ctx: HomeAssistantChatContext, _params: dict[str, object]) -> dict[str, object]:
    result = ctx.service.list_control_requests(user_id=ctx.user_id, role=ctx.role)
    requests = [item for item in (result.get("requests") or []) if item.get("status") == "pending_confirmation"]
    if not requests:
        reply = "Aktuell gibt es keine offenen Home-Assistant-Freigaben."
    else:
        lines = [f"- {item.get('entity_label')}: {item.get('action')} ({item.get('risk_level')})" for item in requests[:5]]
        reply = "Offene Home-Assistant-Freigaben:\n" + "\n".join(lines)
    return {
        "reply": reply,
        "data": {"route": "home_assistant_chat", "intent": "list_open_requests", "action": "list_open_requests", "count": len(requests)},
    }


def _confirm_request(ctx: HomeAssistantChatContext, params: dict[str, object]) -> dict[str, object]:
    request_id = str(params.get("request_id") or "").strip()
    confirm = bool(params.get("confirmed", True))
    target_label = str(params.get("target_label") or "die Aktion").strip() or "die Aktion"
    updated = ctx.service.confirm_control_request(
        request_id,
        {"confirmed": confirm},
        user_id=ctx.user_id,
        role=ctx.role,
    ).get("request") or {}
    entity_label = updated.get("entity_label", target_label)
    return {
        "reply": f"Freigabe für {entity_label} wurde {'bestätigt' if confirm else 'abgelehnt'}.",
        "data": {"route": "home_assistant_chat", "intent": "confirm_request", "action": "confirm_request", "request": updated},
    }


def _create_calendar_item(ctx: HomeAssistantChatContext, params: dict[str, object]) -> dict[str, object]:
    title = str(params.get("title") or "").strip()
    starts_at = str(params.get("starts_at") or "").strip()
    item = ctx.service.add_calendar_item(
        {"title": title, "starts_at": starts_at},
        user_id=ctx.user_id,
        role=ctx.role,
    ).get("item") or {}
    return {
        "reply": f"Kalendereintrag angelegt: {item.get('title', title)} um {item.get('starts_at', starts_at)}.",
        "data": {"route": "home_assistant_chat", "intent": "create_calendar_item", "action": "create_calendar_item", "item": item},
    }


def _list_calendar_items(ctx: HomeAssistantChatContext, _params: dict[str, object]) -> dict[str, object]:
    result = ctx.service.list_calendar_items(user_id=ctx.user_id, role=ctx.role)
    items = result.get("items") or []
    if not items:
        reply = "Im Kalender sind aktuell keine Einträge vorhanden."
    else:
        lines = [f"- {item.get('title')}: {item.get('starts_at')}" for item in items[:5]]
        reply = "Kalendereinträge:\n" + "\n".join(lines)
    return {
        "reply": reply,
        "data": {"route": "home_assistant_chat", "intent": "list_calendar_items", "action": "list_calendar_items", "count": len(items)},
    }


def _create_inbox_item(ctx: HomeAssistantChatContext, params: dict[str, object]) -> dict[str, object]:
    subject = str(params.get("subject") or "").strip()
    item = ctx.service.add_inbox_item(
        {"subject": subject, "from_label": "Jarvis", "summary": subject},
        user_id=ctx.user_id,
        role=ctx.role,
    ).get("item") or {}
    return {
        "reply": f"Inbox-Eintrag angelegt: {item.get('subject', subject)}.",
        "data": {"route": "home_assistant_chat", "intent": "create_inbox_item", "action": "create_inbox_item", "item": item},
    }


def _list_inbox_items(ctx: HomeAssistantChatContext, _params: dict[str, object]) -> dict[str, object]:
    result = ctx.service.list_inbox_items(user_id=ctx.user_id, role=ctx.role)
    items = result.get("items") or []
    if not items:
        reply = "In der Inbox gibt es aktuell keine Einträge."
    else:
        lines = [f"- {item.get('subject')} ({item.get('status')})" for item in items[:5]]
        reply = "Inbox:\n" + "\n".join(lines)
    return {
        "reply": reply,
        "data": {"route": "home_assistant_chat", "intent": "list_inbox_items", "action": "list_inbox_items", "count": len(items)},
    }


def _add_shopping_item(ctx: HomeAssistantChatContext, params: dict[str, object]) -> dict[str, object]:
    title = str(params.get("title") or "").strip()
    item = ctx.service.add_shopping_list_item(
        {"title": title},
        user_id=ctx.user_id,
        role=ctx.role,
    ).get("item") or {}
    return {
        "reply": f"Einkaufslisten-Eintrag angelegt: {item.get('title', title)}.",
        "data": {"route": "home_assistant_chat", "intent": "add_shopping_item", "action": "add_shopping_item", "item": item},
    }


def _list_shopping_items(ctx: HomeAssistantChatContext, _params: dict[str, object]) -> dict[str, object]:
    result = ctx.service.list_shopping_list_items(user_id=ctx.user_id, role=ctx.role)
    items = result.get("items") or []
    if not items:
        reply = "Die Einkaufsliste ist aktuell leer."
    else:
        lines = [f"- {item.get('title')} ({item.get('status')})" for item in items[:5]]
        reply = "Einkaufsliste:\n" + "\n".join(lines)
    return {
        "reply": reply,
        "data": {"route": "home_assistant_chat", "intent": "list_shopping_items", "action": "list_shopping_items", "count": len(items)},
    }


def _create_discovery_candidate(ctx: HomeAssistantChatContext, params: dict[str, object]) -> dict[str, object]:
    label = str(params.get("label") or "").strip()
    kind = str(params.get("kind") or "device").strip() or "device"
    area = str(params.get("area") or "").strip()
    candidate = ctx.service.create_discovery_candidate(
        {"label": label, "suggested_type": kind, "suggested_area": area, "source": "jarvis_chat"},
        user_id=ctx.user_id,
        role=ctx.role,
    ).get("candidate") or {}
    area_hint = f" im Bereich {area}" if area else ""
    return {
        "reply": f"Gerät zur Prüfung angelegt: {candidate.get('label', label)}{area_hint}. Du kannst es jetzt unter Geräte freigeben.",
        "data": {"route": "home_assistant_chat", "intent": "create_discovery_candidate", "action": "create_discovery_candidate", "candidate": candidate},
    }


def _entity_action(ctx: HomeAssistantChatContext, params: dict[str, object]) -> dict[str, object]:
    entity_id = str(params.get("entity_id") or "").strip()
    entity_label = str(params.get("entity_label") or entity_id).strip()
    desired_action = str(params.get("action") or "").strip()
    value = params.get("value")
    remote = bool(params.get("remote", False))
    result = ctx.service.request_entity_action(
        entity_id,
        {"action": desired_action, "value": value, "remote": remote},
        user_id=ctx.user_id,
        role=ctx.role,
    )
    executed = bool(result.get("executed"))
    request = result.get("request") or {}
    reply_action = _humanize_entity_action(desired_action)
    return {
        "reply": (
            f"{entity_label} wurde {reply_action}."
            if executed
            else f"Für {entity_label} wurde eine Freigabe für {desired_action} erstellt."
        ),
        "data": {"route": "home_assistant_chat", "intent": "entity_action", "action": "entity_action", "request": request, "executed": executed},
    }


def _area_entity_action(ctx: HomeAssistantChatContext, params: dict[str, object]) -> dict[str, object]:
    entity_ids = list(params.get("entity_ids") or [])
    entity_labels = list(params.get("entity_labels") or [])
    desired_action = str(params.get("action") or "").strip()
    value = params.get("value")
    remote = bool(params.get("remote", False))
    area = str(params.get("area") or "").strip()

    executed_count = 0
    failed_labels: list[str] = []
    requests: list[dict[str, object]] = []

    for idx, entity_id in enumerate(entity_ids):
        label = entity_labels[idx] if idx < len(entity_labels) else entity_id
        try:
            result = ctx.service.request_entity_action(
                entity_id,
                {"action": desired_action, "value": value, "remote": remote},
                user_id=ctx.user_id,
                role=ctx.role,
            )
            if result.get("executed"):
                executed_count += 1
            requests.append(result.get("request") or {})
        except Exception:
            failed_labels.append(label)

    total = len(entity_ids)
    reply_action = _humanize_entity_action(desired_action)
    area_hint = f" im Bereich {area}" if area else ""
    if failed_labels:
        reply = f"{executed_count} von {total} Geräten{area_hint} wurden {reply_action}. Fehler bei: {', '.join(failed_labels)}."
    elif executed_count == total:
        reply = f"Alle {total} Geräte{area_hint} wurden {reply_action}."
    else:
        reply = f"{executed_count} von {total} Geräten{area_hint} wurden {reply_action}."

    return {
        "reply": reply,
        "data": {
            "route": "home_assistant_chat",
            "intent": "area_entity_action",
            "action": "area_entity_action",
            "executed_count": executed_count,
            "total": total,
            "requests": requests,
        },
    }


def _list_automations(ctx: HomeAssistantChatContext, _params: dict[str, object]) -> dict[str, object]:
    result = ctx.service.list_automation_rules(user_id=ctx.user_id, role=ctx.role)
    automations = result.get("automations") or []
    if not automations:
        reply = "Aktuell sind keine Automationen eingerichtet."
    else:
        lines = [f"- {item.get('name')} ({'aktiv' if item.get('enabled') else 'deaktiviert'})" for item in automations[:5]]
        reply = "Automationen:\n" + "\n".join(lines)
    return {
        "reply": reply,
        "data": {"route": "home_assistant_chat", "intent": "list_automations", "action": "list_automations", "count": len(automations)},
    }


def _create_automation(ctx: HomeAssistantChatContext, params: dict[str, object]) -> dict[str, object]:
    name = str(params.get("name") or "").strip()
    target_area = str(params.get("target_area") or "").strip()
    trigger = str(params.get("trigger") or "manual").strip()
    action_summary = str(params.get("action_summary") or "").strip()
    created = ctx.service.create_automation_rule(
        {
            "name": name,
            "target_area": target_area,
            "trigger": trigger,
            "action_summary": action_summary,
            "enabled": True,
            "risk_level": "medium",
        },
        user_id=ctx.user_id,
        role=ctx.role,
    ).get("automation") or {}
    return {
        "reply": f"Automation angelegt: {created.get('name', name)}.",
        "data": {"route": "home_assistant_chat", "intent": "create_automation", "action": "create_automation", "automation": created},
    }


def _toggle_automation(ctx: HomeAssistantChatContext, params: dict[str, object]) -> dict[str, object]:
    rule_id = str(params.get("rule_id") or "").strip()
    name = str(params.get("name") or rule_id).strip()
    enabled = bool(params.get("enabled", True))
    updated = ctx.service.toggle_automation_rule(
        rule_id,
        {"enabled": enabled},
        user_id=ctx.user_id,
        role=ctx.role,
    ).get("automation") or {}
    return {
        "reply": f"Automation {updated.get('name', name)} wurde {'aktiviert' if enabled else 'deaktiviert'}.",
        "data": {"route": "home_assistant_chat", "intent": "toggle_automation", "action": "toggle_automation", "automation": updated},
    }


def _list_recovery_playbooks(ctx: HomeAssistantChatContext, _params: dict[str, object]) -> dict[str, object]:
    result = ctx.service.list_recovery_playbooks(user_id=ctx.user_id, role=ctx.role)
    playbooks = result.get("playbooks") or []
    if not playbooks:
        reply = "Aktuell sind keine Wiederherstellungsaktionen verfügbar."
    else:
        lines = [f"- {item.get('title')} ({item.get('risk_level')})" for item in playbooks[:5]]
        reply = "Wiederherstellungen:\n" + "\n".join(lines)
    return {
        "reply": reply,
        "data": {"route": "home_assistant_chat", "intent": "list_recovery_playbooks", "action": "list_recovery_playbooks", "count": len(playbooks)},
    }


def _execute_recovery_playbook(ctx: HomeAssistantChatContext, params: dict[str, object]) -> dict[str, object]:
    playbook_id = str(params.get("playbook_id") or "").strip()
    title = str(params.get("title") or playbook_id).strip()
    result = ctx.service.execute_recovery_playbook(playbook_id, user_id=ctx.user_id, role=ctx.role)
    return {
        "reply": f"Wiederherstellung ausgeführt: {result.get('playbook', {}).get('title', title)}.",
        "data": {"route": "home_assistant_chat", "intent": "execute_recovery_playbook", "action": "execute_recovery_playbook", "result": result},
    }


def _list_system_targets(ctx: HomeAssistantChatContext, _params: dict[str, object]) -> dict[str, object]:
    result = ctx.service.list_system_targets(user_id=ctx.user_id, role=ctx.role)
    targets = result.get("targets") or []
    if not targets:
        reply = "Aktuell sind keine Systeme registriert."
    else:
        lines = [f"- {item.get('label')} ({item.get('status', 'unknown')})" for item in targets[:5]]
        reply = "Systeme:\n" + "\n".join(lines)
    return {
        "reply": reply,
        "data": {"route": "home_assistant_chat", "intent": "list_system_targets", "action": "list_system_targets", "count": len(targets)},
    }


def _request_system_action(ctx: HomeAssistantChatContext, params: dict[str, object]) -> dict[str, object]:
    target_id = str(params.get("target_id") or "").strip()
    label = str(params.get("label") or target_id).strip()
    action = str(params.get("action") or "").strip()
    result = ctx.service.request_system_target_action(
        target_id,
        {"action": action},
        user_id=ctx.user_id,
        role=ctx.role,
    )
    request = result.get("request") or {}
    executed = bool(result.get("executed"))
    return {
        "reply": f"{label} wurde {action}." if executed else f"Für {label} wurde eine Freigabe für {action} erstellt.",
        "data": {"route": "home_assistant_chat", "intent": "request_system_action", "action": "request_system_action", "request": request, "executed": executed},
    }


HOME_ASSISTANT_CHAT_ACTION_REGISTRY: dict[str, HomeAssistantChatActionDefinition] = {
    "sync_entities": HomeAssistantChatActionDefinition(
        name="sync_entities",
        summary="Synchronisiert verwaltete Home-Assistant-Geräte.",
        required_fields=(),
        executor=_sync_entities,
    ),
    "list_open_requests": HomeAssistantChatActionDefinition(
        name="list_open_requests",
        summary="Listet offene Home-Assistant-Freigaben.",
        required_fields=(),
        executor=_list_open_requests,
    ),
    "confirm_request": HomeAssistantChatActionDefinition(
        name="confirm_request",
        summary="Bestätigt oder lehnt eine offene Freigabe ab.",
        required_fields=("request_id", "confirmed"),
        executor=_confirm_request,
        risk_level="high",
        requires_confirmation=True,
    ),
    "create_calendar_item": HomeAssistantChatActionDefinition(
        name="create_calendar_item",
        summary="Legt einen Kalendereintrag an.",
        required_fields=("title", "starts_at"),
        executor=_create_calendar_item,
    ),
    "list_calendar_items": HomeAssistantChatActionDefinition(
        name="list_calendar_items",
        summary="Listet Kalendereinträge.",
        required_fields=(),
        executor=_list_calendar_items,
    ),
    "create_inbox_item": HomeAssistantChatActionDefinition(
        name="create_inbox_item",
        summary="Legt einen Inbox-Eintrag an.",
        required_fields=("subject",),
        executor=_create_inbox_item,
    ),
    "list_inbox_items": HomeAssistantChatActionDefinition(
        name="list_inbox_items",
        summary="Listet Inbox-Einträge.",
        required_fields=(),
        executor=_list_inbox_items,
    ),
    "add_shopping_item": HomeAssistantChatActionDefinition(
        name="add_shopping_item",
        summary="Legt einen Einkaufslisten-Eintrag an.",
        required_fields=("title",),
        executor=_add_shopping_item,
    ),
    "list_shopping_items": HomeAssistantChatActionDefinition(
        name="list_shopping_items",
        summary="Listet Einkaufslisten-Einträge.",
        required_fields=(),
        executor=_list_shopping_items,
    ),
    "create_discovery_candidate": HomeAssistantChatActionDefinition(
        name="create_discovery_candidate",
        summary="Legt ein neues Gerät zur Prüfung an.",
        required_fields=("label", "kind"),
        executor=_create_discovery_candidate,
        risk_level="medium",
    ),
    "entity_action": HomeAssistantChatActionDefinition(
        name="entity_action",
        summary="Führt eine Geräteaktion aus oder erstellt eine Freigabe.",
        required_fields=("entity_id", "entity_label", "action", "value"),
        executor=_entity_action,
        risk_level="medium",
    ),
    "list_automations": HomeAssistantChatActionDefinition(
        name="list_automations",
        summary="Listet Automationen.",
        required_fields=(),
        executor=_list_automations,
    ),
    "create_automation": HomeAssistantChatActionDefinition(
        name="create_automation",
        summary="Legt eine Automation an.",
        required_fields=("name",),
        executor=_create_automation,
        risk_level="medium",
    ),
    "toggle_automation": HomeAssistantChatActionDefinition(
        name="toggle_automation",
        summary="Aktiviert oder deaktiviert eine Automation.",
        required_fields=("rule_id", "enabled"),
        executor=_toggle_automation,
        risk_level="medium",
    ),
    "list_recovery_playbooks": HomeAssistantChatActionDefinition(
        name="list_recovery_playbooks",
        summary="Listet Wiederherstellungsaktionen.",
        required_fields=(),
        executor=_list_recovery_playbooks,
    ),
    "execute_recovery_playbook": HomeAssistantChatActionDefinition(
        name="execute_recovery_playbook",
        summary="Führt eine Wiederherstellungsaktion aus.",
        required_fields=("playbook_id",),
        executor=_execute_recovery_playbook,
        risk_level="medium",
    ),
    "list_system_targets": HomeAssistantChatActionDefinition(
        name="list_system_targets",
        summary="Listet registrierte Systeme.",
        required_fields=(),
        executor=_list_system_targets,
    ),
    "request_system_action": HomeAssistantChatActionDefinition(
        name="request_system_action",
        summary="Fordert eine Systemaktion an.",
        required_fields=("target_id", "action"),
        executor=_request_system_action,
        risk_level="high",
        requires_confirmation=True,
    ),
    "area_entity_action": HomeAssistantChatActionDefinition(
        name="area_entity_action",
        summary="Führt eine Geräteaktion auf allen Geräten eines Bereichs aus.",
        required_fields=("entity_ids", "action"),
        executor=_area_entity_action,
        risk_level="medium",
    ),
}
