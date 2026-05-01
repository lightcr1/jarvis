from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re

from .chat_actions import HOME_ASSISTANT_CHAT_ACTION_REGISTRY, HomeAssistantChatContext
from .service import DEVICE_ACTION_PROFILES


def normalize_lookup(text: str) -> str:
    value = (text or "").lower()
    replacements = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}
    for source, target in replacements.items():
        value = value.replace(source, target)
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def _has_time_reference(text: str) -> bool:
    lowered = text.lower()
    return bool(
        re.search(r"\b(\d{1,2})[:.](\d{2})\b", lowered)
        or re.search(r"\b(\d{1,2})[./-](\d{1,2})(?:[./-](\d{2,4}))?\b", lowered)
        or any(
            token in lowered
            for token in (
                "heute",
                "morgen",
                "übermorgen",
                "uebermorgen",
                "montag",
                "dienstag",
                "mittwoch",
                "donnerstag",
                "freitag",
                "samstag",
                "sonntag",
                "morgens",
                "mittag",
                "mittags",
                "nachmittags",
                "abends",
                "früh",
                "frueh",
            )
        )
    )


def parse_iso_from_text(text: str) -> str:
    lowered = text.lower()
    now = datetime.now(timezone.utc)
    target_day = now.date()
    weekday_map = {
        "montag": 0,
        "dienstag": 1,
        "mittwoch": 2,
        "donnerstag": 3,
        "freitag": 4,
        "samstag": 5,
        "sonntag": 6,
    }
    if "übermorgen" in lowered or "uebermorgen" in lowered:
        target_day = (now + timedelta(days=2)).date()
    elif "morgen" in lowered:
        target_day = (now + timedelta(days=1)).date()
    elif "heute" in lowered:
        target_day = now.date()
    else:
        weekday_match = next((value for key, value in weekday_map.items() if key in lowered), None)
        if weekday_match is not None:
            delta = (weekday_match - now.weekday()) % 7
            if delta == 0:
                delta = 7
            target_day = (now + timedelta(days=delta)).date()

    absolute_match = re.search(r"\b(\d{1,2})[./-](\d{1,2})(?:[./-](\d{2,4}))?\b", lowered)
    if absolute_match:
        day = int(absolute_match.group(1))
        month = int(absolute_match.group(2))
        year_raw = absolute_match.group(3)
        year = int(year_raw) if year_raw else now.year
        if year < 100:
            year += 2000
        target_day = datetime(year, month, day, tzinfo=timezone.utc).date()

    time_match = re.search(r"\b(\d{1,2})[:.](\d{2})\b", lowered)
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2))
    elif "mittags" in lowered or "mittag" in lowered:
        hour, minute = 12, 0
    elif "nachmittags" in lowered:
        hour, minute = 15, 0
    elif "abends" in lowered or "abend" in lowered:
        hour, minute = 19, 0
    elif "morgens" in lowered or "früh" in lowered or "frueh" in lowered:
        hour, minute = 8, 0
    else:
        hour, minute = 9, 0
    return datetime(target_day.year, target_day.month, target_day.day, hour, minute, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def _build_action_value(action: str) -> str:
    if "off" in action:
        return "off"
    if action == "lock":
        return "locked"
    if "unlock" in action:
        return "unlocked"
    if "disarm" in action:
        return "disarmed"
    if "close" in action:
        return "closed"
    if "arm" in action:
        return "armed"
    if "open" in action:
        return "open"
    if "record" in action:
        return "recording"
    if "stream" in action:
        return "streaming"
    return "on"


def _find_entity_by_text(ctx: HomeAssistantChatContext) -> dict[str, object] | None:
    entities = ctx.service.list_managed_entities(user_id=ctx.user_id, role=ctx.role).get("entities") or []
    for item in entities:
        label = normalize_lookup(str(item.get("label") or ""))
        if label and label in ctx.normalized:
            return item
    return None


def _device_action_from_text(normalized: str, kind: str) -> str | None:
    actions = {str(item.get("action") or "") for item in DEVICE_ACTION_PROFILES.get(kind, {}).get("actions", [])}
    candidates = (
        ("turn_off", ("ausschalt", " aus", "aus ", "deaktivier")),
        ("turn_on", ("einschalt", " an", "an ", "aktivier")),
        ("unlock", ("entriegel", "entriegl", "entsperr", " unlock", "oeffne schloss", "öffne schloss")),
        ("lock", ("verriegel", "sperr", " lock")),
        ("open", ("öffne", "oeffne", "aufmach")),
        ("close", ("schließ", "schliess", "zumach")),
        ("arm", (" unscharf", " scharf", " arm", "aktivieren alarm")),
        ("disarm", ("entschaerf", "entschärf", " disarm", "deaktivieren alarm", "unscharf")),
        ("record", ("aufnehm", "record")),
        ("stream", ("stream", "livestream", "kamera zeigen")),
    )
    for action, variants in candidates:
        if action in actions and any(variant in normalized for variant in variants):
            return action
    return None


def _extract_tail(text: str, prefixes: tuple[str, ...]) -> str:
    stripped = text.strip().rstrip(".")
    lowered = stripped.lower()
    for prefix in prefixes:
        if lowered.startswith(prefix):
            return stripped[len(prefix) :].strip()
    return stripped


def _strip_jarvis_prefix(text: str) -> str:
    return re.sub(r"^[^a-zA-Z0-9äöüÄÖÜß]*jarvis[,\s:!-]*", "", text.strip(), flags=re.IGNORECASE).strip()


def _clean_subject_like_text(text: str, generic_terms: tuple[str, ...]) -> str:
    value = _strip_jarvis_prefix(text).rstrip(".")
    generic_pattern = r"^(?:einen|einem|eine|einer|den|dem|das)?\s*(?:" + "|".join(re.escape(term) for term in generic_terms) + r")\b"
    return re.sub(generic_pattern, "", value, flags=re.IGNORECASE).strip(" ,.-")


def _pending_response(action: str, params: dict[str, object], missing_fields: list[str], reply: str) -> dict[str, object]:
    return {
        "reply": reply,
        "data": {
            "route": "home_assistant_chat",
            "error": "missing_fields",
            "action": action,
            "missing_fields": missing_fields,
            "follow_up": {
                "action": action,
                "params": params,
                "missing_fields": missing_fields,
            },
        },
    }


def _resolve_request(ctx: HomeAssistantChatContext) -> dict[str, object] | None:
    normalized = ctx.normalized
    if not any(word in normalized for word in ("bestaetige", "bestaetigen", "genehmige", "erlaube", "ablehnen", "lehne", "verweigere")):
        return None
    result = ctx.service.list_control_requests(user_id=ctx.user_id, role=ctx.role)
    requests = [item for item in (result.get("requests") or []) if item.get("status") == "pending_confirmation"]
    if not requests:
        return None
    confirm = not any(word in normalized for word in ("ablehnen", "lehne", "verweigere"))
    target_request = requests[0]
    for item in requests:
        label = normalize_lookup(str(item.get("entity_label") or ""))
        if label and label in normalized:
            target_request = item
            break
    return {
        "action": "confirm_request",
        "params": {
            "request_id": str(target_request.get("id") or ""),
            "confirmed": confirm,
            "target_label": str(target_request.get("entity_label") or ""),
        },
    }


def _resolve_sync_entities(ctx: HomeAssistantChatContext) -> dict[str, object] | None:
    cleaned = ctx.cleaned
    if ("synchron" not in cleaned and "sync" not in cleaned) or not any(word in cleaned for word in ("gerät", "geräte", "entities", "entity")):
        return None
    return {"action": "sync_entities", "params": {}}


def _resolve_list_open_requests(ctx: HomeAssistantChatContext) -> dict[str, object] | None:
    cleaned = ctx.cleaned
    if not any(word in cleaned for word in ("freigaben", "requests", "request", "warteschlange")):
        return None
    if not any(word in cleaned for word in ("zeige", "zeig", "liste", "offen", "welche", "offene")):
        return None
    return {"action": "list_open_requests", "params": {}}


def _resolve_calendar(ctx: HomeAssistantChatContext) -> dict[str, object] | None:
    cleaned = ctx.cleaned
    raw = _strip_jarvis_prefix(ctx.text)
    if not any(word in cleaned for word in ("kalender", "termin")):
        return None
    create_requested = any(word in cleaned for word in ("erstelle", "anlegen", "anlege", "füge", "fuege", "plane"))
    if not create_requested and any(word in cleaned for word in ("zeige", "zeig", "liste", "welche", "was steht", "was ist")):
        return {"action": "list_calendar_items", "params": {}}
    if not create_requested:
        return None
    title_match = re.search(r"(?:für|fuer)\s+(.+)$", raw, re.IGNORECASE)
    title = (title_match.group(1).strip() if title_match else _extract_tail(raw, ("erstelle", "lege", "anlegen", "plane"))).rstrip(".")
    title = re.sub(r"^(?:einen|einem|einer|einen|den|dem|das)?\s*(?:kalendereintrag|termin)\b", "", title, flags=re.IGNORECASE).strip(" ,.-")
    title = re.sub(r"\b(heute|morgen|übermorgen|uebermorgen|montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag)\b", "", title, flags=re.IGNORECASE).strip(" ,.-")
    title = re.sub(r"\b(um\s+\d{1,2}[:.]\d{2}|morgens|mittags|nachmittags|abends|früh|frueh)\b", "", title, flags=re.IGNORECASE).strip(" ,.-")
    missing_fields: list[str] = []
    if not title:
        missing_fields.append("title")
    params: dict[str, object] = {"title": title}
    if _has_time_reference(cleaned):
        params["starts_at"] = parse_iso_from_text(cleaned)
    else:
        missing_fields.append("starts_at")
    return {"action": "create_calendar_item", "params": params, "missing_fields": missing_fields}


def _resolve_inbox(ctx: HomeAssistantChatContext) -> dict[str, object] | None:
    cleaned = ctx.cleaned
    raw = _strip_jarvis_prefix(ctx.text)
    if not any(word in cleaned for word in ("inbox", "mail", "email", "nachricht")):
        return None
    create_requested = any(word in cleaned for word in ("erstelle", "anlegen", "anlege", "füge", "fuege", "schreibe"))
    if not create_requested and any(word in cleaned for word in ("zeige", "zeig", "liste", "welche", "offen", "ungelesen")):
        return {"action": "list_inbox_items", "params": {}}
    if not create_requested:
        return None
    subject_match = re.search(r"(?:für|fuer)\s+(.+)$", raw, re.IGNORECASE)
    subject = (subject_match.group(1).strip() if subject_match else _extract_tail(raw, ("erstelle", "schreibe", "füge", "fuege"))).rstrip(".")
    subject = re.sub(r"^(?:eine|einen|einer|einem)?\s*(?:inbox(?:-nachricht)?|nachricht|mail|email)\b", "", subject, flags=re.IGNORECASE).strip(" ,.-")
    missing_fields: list[str] = []
    if not subject:
        missing_fields.append("subject")
    return {"action": "create_inbox_item", "params": {"subject": subject}, "missing_fields": missing_fields}


def _resolve_shopping(ctx: HomeAssistantChatContext) -> dict[str, object] | None:
    cleaned = ctx.cleaned
    if not any(word in cleaned for word in ("einkauf", "einkaufsliste")):
        return None
    create_requested = any(word in cleaned for word in ("füge", "fuege", "hinzu", "setze", "pack"))
    if not create_requested and any(word in cleaned for word in ("zeige", "zeig", "liste", "was fehlt", "was ist")):
        return {"action": "list_shopping_items", "params": {}}
    if not create_requested:
        return None
    title_match = re.search(r"(?:füge|fuege|packe?|setze)\s+(.+?)(?:\s+(?:zur|auf die|in die)\s+einkaufsliste)?$", ctx.text.strip(), re.IGNORECASE)
    title = (title_match.group(1).strip() if title_match else ctx.text.strip()).rstrip(".")
    title = re.sub(r"^(?:etwas|einen|eine|den|das)?\s*(?:zur|auf die|in die)?\s*(?:einkaufsliste|liste)\b", "", title, flags=re.IGNORECASE).strip(" ,.-")
    title = re.sub(r"\bhinzu\b$", "", title, flags=re.IGNORECASE).strip(" ,.-")
    missing_fields: list[str] = []
    if not title:
        missing_fields.append("title")
    return {"action": "add_shopping_item", "params": {"title": title}, "missing_fields": missing_fields}


def _resolve_discovery(ctx: HomeAssistantChatContext) -> dict[str, object] | None:
    cleaned = ctx.cleaned
    if not any(word in cleaned for word in ("lampe", "licht", "gerät", "geraet", "device")):
        return None
    if not any(word in cleaned for word in ("füge", "fuege", "hinzu", "add")):
        return None
    area_match = re.search(r"\b(?:im|in der|in dem)\s+([a-zA-ZäöüÄÖÜß0-9_-]+)", ctx.text, re.IGNORECASE)
    area = area_match.group(1).strip() if area_match else ""
    kind = "light" if any(word in cleaned for word in ("lampe", "licht")) else "device"
    label_match = re.search(r"(?:füge|fuege|add)\s+(?:die|das|den)?\s*(.+?)(?:\s+(?:im|in der|in dem)\b|$)", ctx.text.strip(), re.IGNORECASE)
    label = (label_match.group(1).strip() if label_match else ctx.text.strip()).rstrip(".")
    return {"action": "create_discovery_candidate", "params": {"label": label, "kind": kind, "area": area}}


def _resolve_entity_action(ctx: HomeAssistantChatContext) -> dict[str, object] | None:
    normalized = ctx.normalized
    if not any(word in normalized for word in (" an", " aus", " einschalten", " ausschalten", " schalte ", "schalte", " mach ", "mache", "oeff", "öff", "schliess", "schließ", "verriegel", "entriegel", "entriegl", "entsperr", "alarm", "kamera", "aufnahme", "stream")):
        return None
    target_entity = _find_entity_by_text(ctx)
    if not target_entity:
        return None
    kind = str(target_entity.get("kind") or "").strip().lower()
    desired_action = _device_action_from_text(normalized, kind)
    if not desired_action:
        return {
            "action": "missing_entity_action_details",
            "params": {
                "entity_id": str(target_entity.get("entity_id") or ""),
                "entity_label": str(target_entity.get("label") or ""),
                "kind": kind,
            },
        }
    remote_actions = {"unlock", "lock", "open", "close", "arm", "disarm", "record", "stream"}
    return {
        "action": "entity_action",
        "params": {
            "entity_id": str(target_entity.get("entity_id") or ""),
            "entity_label": str(target_entity.get("label") or ""),
            "action": desired_action,
            "value": _build_action_value(desired_action),
            "remote": desired_action in remote_actions,
        },
    }
    return None


def _continue_pending_action(ctx: HomeAssistantChatContext, pending_action: dict[str, object]) -> dict[str, object]:
    action = str(pending_action.get("action") or "").strip()
    params = dict(pending_action.get("params") or {})
    missing_fields = list(pending_action.get("missing_fields") or [])
    cleaned = ctx.cleaned

    if action == "create_calendar_item":
        if "title" in missing_fields:
            title = re.sub(r"\b(heute|morgen|übermorgen|uebermorgen|montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag)\b", "", ctx.text, flags=re.IGNORECASE)
            title = re.sub(r"\b(um\s+\d{1,2}[:.]\d{2}|morgens|mittags|nachmittags|abends|früh|frueh)\b", "", title, flags=re.IGNORECASE).strip(" ,.-")
            if title:
                params["title"] = title
                missing_fields = [field for field in missing_fields if field != "title"]
        if "starts_at" in missing_fields and _has_time_reference(cleaned):
            params["starts_at"] = parse_iso_from_text(cleaned)
            missing_fields = [field for field in missing_fields if field != "starts_at"]
        if missing_fields:
            if "title" in missing_fields and "starts_at" in missing_fields:
                return _pending_response(action, params, missing_fields, "Für den Termin brauche ich noch einen Titel und eine Zeitangabe, zum Beispiel: 'morgen um 09:00 für Wartung'.")
            if "title" in missing_fields:
                return _pending_response(action, params, missing_fields, "Wie soll der Kalendereintrag heißen?")
            return _pending_response(action, params, missing_fields, "Wann soll der Termin stattfinden? Zum Beispiel: 'morgen um 09:00' oder 'am Freitag abends'.")
        return {"action": action, "params": params}

    if action == "create_inbox_item":
        if "subject" in missing_fields:
            subject = _clean_subject_like_text(ctx.text, ("inbox", "inbox-nachricht", "nachricht", "mail", "email"))
            if subject:
                params["subject"] = subject
                missing_fields = [field for field in missing_fields if field != "subject"]
        if missing_fields:
            return _pending_response(action, params, missing_fields, "Wie soll die Inbox-Nachricht heißen?")
        return {"action": action, "params": params}

    if action == "add_shopping_item":
        if "title" in missing_fields:
            title = _clean_subject_like_text(ctx.text, ("einkaufsliste", "liste"))
            if title:
                params["title"] = title
                missing_fields = [field for field in missing_fields if field != "title"]
        if missing_fields:
            return _pending_response(action, params, missing_fields, "Was soll ich auf die Einkaufsliste setzen?")
        return {"action": action, "params": params}

    if action == "create_automation":
        if "name" in missing_fields:
            name = _clean_subject_like_text(ctx.text, ("automation", "regel"))
            if name:
                params["name"] = name
                missing_fields = [field for field in missing_fields if field != "name"]
        if missing_fields:
            return _pending_response(action, params, missing_fields, "Wie soll die Automation heißen?")
        return {"action": action, "params": params}

    if action == "entity_action":
        kind = str(params.get("kind") or "").strip().lower()
        desired_action = _device_action_from_text(ctx.normalized, kind)
        if desired_action:
            params["action"] = desired_action
            params["value"] = _build_action_value(desired_action)
            params["remote"] = desired_action in {"unlock", "lock", "open", "close", "arm", "disarm", "record", "stream"}
            return {"action": action, "params": params}
        available_actions = [str(item.get("action") or "") for item in DEVICE_ACTION_PROFILES.get(kind, {}).get("actions", [])]
        return {
            "reply": f"Ich brauche noch die gewünschte Aktion für {params.get('entity_label', 'dieses Gerät')}. Mögliche Aktionen sind: {', '.join(available_actions)}.",
            "data": {
                "route": "home_assistant_chat",
                "error": "missing_entity_action",
                "follow_up": {
                    "action": action,
                    "params": params,
                    "missing_fields": ["action"],
                },
            },
        }

    return {"reply": "Diese Home-Assistant-Rückfrage konnte nicht mehr aufgelöst werden.", "data": {"route": "home_assistant_chat", "error": "pending_action_unsupported"}}


def _resolve_automation(ctx: HomeAssistantChatContext) -> dict[str, object] | None:
    normalized = ctx.normalized
    cleaned = ctx.cleaned
    raw = _strip_jarvis_prefix(ctx.text)
    if not any(word in normalized for word in ("automation", "automationen", "automationen", "regel", "regeln")):
        return None
    if any(word in cleaned for word in ("zeige", "zeig", "liste", "welche")):
        return {"action": "list_automations", "params": {}}
    automations = ctx.service.list_automation_rules(user_id=ctx.user_id, role=ctx.role).get("automations") or []
    if any(word in normalized for word in ("deaktivier", "deaktiviere", "ausschalten", "abschalten")):
        enabled = False
    elif any(word in normalized for word in ("aktivier", "aktiviere", "einschalten")):
        enabled = True
    else:
        enabled = None
    if enabled is not None:
        for item in automations:
            name = normalize_lookup(str(item.get("name") or ""))
            if name and name in normalized:
                return {
                    "action": "toggle_automation",
                    "params": {"rule_id": str(item.get("id") or ""), "name": str(item.get("name") or ""), "enabled": enabled},
                }
    if not any(word in cleaned for word in ("erstelle", "anlegen", "anlege")):
        return None
    name_match = re.search(r"(?:automation|regel)\s+(.+?)(?:\s+(?:im|für|fuer)\s+([a-zA-ZäöüÄÖÜß0-9_-]+))?$", raw, re.IGNORECASE)
    if name_match:
        name = name_match.group(1).strip().rstrip(".")
        target_area = (name_match.group(2) or "").strip()
    else:
        name = _extract_tail(raw, ("erstelle", "anlegen", "anlege")).rstrip(".")
        target_area = ""
    name = re.sub(r"^(?:eine|einen|einer|einem)?\s*(?:automation|regel)\b", "", name, flags=re.IGNORECASE).strip(" ,.-")
    missing_fields: list[str] = []
    if not name:
        missing_fields.append("name")
    return {
        "action": "create_automation",
        "params": {"name": name, "target_area": target_area, "trigger": "manual", "action_summary": "Via Jarvis erstellt"},
        "missing_fields": missing_fields,
    }


def _resolve_recovery(ctx: HomeAssistantChatContext) -> dict[str, object] | None:
    normalized = ctx.normalized
    if not any(word in normalized for word in ("wiederherstellung", "recovery", "playbook", "reparatur")):
        return None
    playbooks = ctx.service.list_recovery_playbooks(user_id=ctx.user_id, role=ctx.role).get("playbooks") or []
    if any(word in normalized for word in ("zeige", "zeig", "liste", "welche")):
        return {"action": "list_recovery_playbooks", "params": {}}
    if not any(word in normalized for word in ("starte", "fuehre", "führe", "aus", "execute")):
        return None
    for item in playbooks:
        title = normalize_lookup(str(item.get("title") or ""))
        playbook_id = normalize_lookup(str(item.get("id") or ""))
        if (title and title in normalized) or (playbook_id and playbook_id in normalized):
            return {"action": "execute_recovery_playbook", "params": {"playbook_id": str(item.get("id") or ""), "title": str(item.get("title") or "")}}
    return None


def _resolve_system_target(ctx: HomeAssistantChatContext) -> dict[str, object] | None:
    normalized = ctx.normalized
    if not any(word in normalized for word in ("system", "systeme", "pc", "server", "rechner")):
        return None
    targets = ctx.service.list_system_targets(user_id=ctx.user_id, role=ctx.role).get("targets") or []
    if any(word in normalized for word in ("zeige", "zeig", "liste", "welche")):
        return {"action": "list_system_targets", "params": {}}
    action_map = {
        "restart": ("restart", "neu starten", "reboot", " starte ", " neu"),
        "shutdown": ("shutdown", "herunterfahren", "ausschalten"),
        "wake": ("wake", "aufwecken", "starten"),
    }
    desired_action = None
    for action, variants in action_map.items():
        if any(variant in normalized for variant in variants):
            desired_action = action
            break
    if not desired_action:
        return None
    for item in targets:
        label = normalize_lookup(str(item.get("label") or ""))
        if label and label in normalized:
            return {"action": "request_system_action", "params": {"target_id": str(item.get("id") or ""), "label": str(item.get("label") or ""), "action": desired_action}}
    return None


RESOLVERS = (
    _resolve_sync_entities,
    _resolve_list_open_requests,
    _resolve_request,
    _resolve_calendar,
    _resolve_inbox,
    _resolve_shopping,
    _resolve_discovery,
    _resolve_entity_action,
    _resolve_automation,
    _resolve_recovery,
    _resolve_system_target,
)


def execute_home_assistant_chat_intent(service: object, text: str, *, user_id: str | None, role: str | None, pending_action: dict | None = None) -> dict | None:
    cleaned = re.sub(r"^[^a-zA-Z0-9äöüÄÖÜß]*jarvis[,\s:!-]*", "", text.strip().lower()).strip()
    ctx = HomeAssistantChatContext(service=service, text=text, cleaned=cleaned, normalized=normalize_lookup(cleaned), user_id=user_id, role=role)
    if pending_action:
        resolved_pending = _continue_pending_action(ctx, pending_action)
        if resolved_pending.get("reply"):
            return resolved_pending
        action_name = str(resolved_pending.get("action") or "").strip()
        params = dict(resolved_pending.get("params") or {})
        definition = HOME_ASSISTANT_CHAT_ACTION_REGISTRY.get(action_name)
        if definition:
            try:
                return definition.executor(ctx, params)
            except PermissionError as exc:
                return {"reply": str(exc), "data": {"error": "permission_denied", "route": "home_assistant_chat", "detail": str(exc), "action": action_name}}
            except LookupError as exc:
                return {"reply": str(exc), "data": {"error": "not_found", "route": "home_assistant_chat", "detail": str(exc), "action": action_name}}
            except ValueError as exc:
                return {"reply": str(exc), "data": {"error": "validation_error", "route": "home_assistant_chat", "detail": str(exc), "action": action_name}}
    for resolver in RESOLVERS:
        try:
            resolved = resolver(ctx)
        except PermissionError as exc:
            return {"reply": str(exc), "data": {"error": "permission_denied", "route": "home_assistant_chat", "detail": str(exc)}}
        except LookupError as exc:
            return {"reply": str(exc), "data": {"error": "not_found", "route": "home_assistant_chat", "detail": str(exc)}}
        except ValueError as exc:
            return {"reply": str(exc), "data": {"error": "validation_error", "route": "home_assistant_chat", "detail": str(exc)}}
        if not resolved:
            continue
        action_name = str(resolved.get("action") or "").strip()
        params = dict(resolved.get("params") or {})
        definition = HOME_ASSISTANT_CHAT_ACTION_REGISTRY.get(action_name)
        if action_name == "missing_entity_action_details":
            entity_label = str(params.get("entity_label") or "dieses Gerät")
            kind = str(params.get("kind") or "device")
            actions = [str(item.get("action") or "") for item in DEVICE_ACTION_PROFILES.get(kind, {}).get("actions", [])]
            if actions:
                return {
                    "reply": f"Was soll ich mit {entity_label} machen? Mögliche Aktionen sind: {', '.join(actions)}.",
                    "data": {
                        "route": "home_assistant_chat",
                        "error": "missing_entity_action",
                        "entity_label": entity_label,
                        "available_actions": actions,
                        "follow_up": {
                            "action": "entity_action",
                            "params": {
                                "entity_id": str(params.get("entity_id") or ""),
                                "entity_label": entity_label,
                                "kind": kind,
                            },
                            "missing_fields": ["action"],
                        },
                    },
                }
            return {
                "reply": f"Für {entity_label} habe ich keine steuerbaren Aktionen gefunden.",
                "data": {"route": "home_assistant_chat", "error": "missing_entity_action", "entity_label": entity_label, "available_actions": []},
            }
        if not definition:
            continue
        unresolved_missing = list(resolved.get("missing_fields") or [])
        if unresolved_missing:
            if action_name == "create_calendar_item":
                if "title" in unresolved_missing and "starts_at" in unresolved_missing:
                    return _pending_response(action_name, params, unresolved_missing, "Für den Kalendereintrag brauche ich noch einen Titel und eine Zeitangabe, zum Beispiel: 'morgen um 09:00 für Wartung'.")
                if "title" in unresolved_missing:
                    return _pending_response(action_name, params, unresolved_missing, "Wie soll der Kalendereintrag heißen?")
                return _pending_response(action_name, params, unresolved_missing, "Wann soll der Termin stattfinden? Zum Beispiel: 'morgen um 09:00' oder 'am Freitag abends'.")
            if action_name == "create_inbox_item":
                return _pending_response(action_name, params, unresolved_missing, "Wie soll die Inbox-Nachricht heißen?")
            if action_name == "add_shopping_item":
                return _pending_response(action_name, params, unresolved_missing, "Was soll ich auf die Einkaufsliste setzen?")
            if action_name == "create_automation":
                return _pending_response(action_name, params, unresolved_missing, "Wie soll die Automation heißen?")
        missing = [field for field in definition.required_fields if params.get(field) in (None, "")]
        if missing:
            if action_name == "create_calendar_item":
                return _pending_response(action_name, params, missing, "Für den Kalendereintrag brauche ich noch einen Titel oder eine Zeitangabe, zum Beispiel: 'Jarvis, erstelle morgen um 09:00 einen Termin für Wartung'.")
            return {
                "reply": f"Für diese Home-Assistant-Aktion fehlen noch Angaben: {', '.join(missing)}.",
                "data": {"error": "missing_fields", "route": "home_assistant_chat", "action": action_name, "missing_fields": missing},
            }
        try:
            return definition.executor(ctx, params)
        except PermissionError as exc:
            return {"reply": str(exc), "data": {"error": "permission_denied", "route": "home_assistant_chat", "detail": str(exc), "action": action_name}}
        except LookupError as exc:
            return {"reply": str(exc), "data": {"error": "not_found", "route": "home_assistant_chat", "detail": str(exc), "action": action_name}}
        except ValueError as exc:
            return {"reply": str(exc), "data": {"error": "validation_error", "route": "home_assistant_chat", "detail": str(exc), "action": action_name}}
    return None
