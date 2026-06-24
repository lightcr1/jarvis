from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
import re

from .chat_actions import HOME_ASSISTANT_CHAT_ACTION_REGISTRY, HomeAssistantChatContext
from .service import DEVICE_ACTION_PROFILES

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Synonym tables — normalize before intent matching
# ---------------------------------------------------------------------------

DEVICE_KIND_SYNONYMS: dict[str, str] = {
    # climate / AC
    "ac": "climate",
    "aircon": "climate",
    "air con": "climate",
    "air conditioning": "climate",
    "air conditioner": "climate",
    "klimaanlage": "climate",
    "klima": "climate",
    "heizung": "climate",
    "heater": "climate",
    "heating": "climate",
    "heat": "climate",
    "boiler": "climate",
    "thermostat": "climate",
    "temperature": "climate",
    "temperatur": "climate",
    # lights
    "lights": "light",
    "light": "light",
    "lighting": "light",
    "lamp": "light",
    "lamps": "light",
    "lampe": "light",
    "lampen": "light",
    "licht": "light",
    "lichter": "light",
    "bulb": "light",
    "bulbs": "light",
    "leuchtmittel": "light",
    "beleuchtung": "light",
    # media
    "tv": "media",
    "telly": "media",
    "television": "media",
    "screen": "media",
    "display": "media",
    "fernseher": "media",
    "fernsehen": "media",
    "speaker": "media",
    "lautsprecher": "media",
    # covers / blinds
    "blinds": "cover",
    "blind": "cover",
    "shutter": "cover",
    "shutters": "cover",
    "shade": "cover",
    "shades": "cover",
    "curtains": "cover",
    "curtain": "cover",
    "roller blind": "cover",
    "rollo": "cover",
    "rolllade": "cover",
    "rollläden": "cover",
    "jalousie": "cover",
    "jalousien": "cover",
    "vorhang": "cover",
    "vorhänge": "cover",
    # locks
    "lock": "lock",
    "door lock": "lock",
    "front door": "lock",
    "back door": "lock",
    "türschloss": "lock",
    "schloss": "lock",
    "haustür": "lock",
    # fans
    "fan": "fan",
    "ceiling fan": "fan",
    "ventilation": "fan",
    "ventilator": "fan",
    "lüfter": "fan",
    # switches / appliances (note: "switch" as a word is excluded — it's a verb in most HA commands)
    "plug": "switch",
    "socket": "switch",
    "outlet": "switch",
    "power": "switch",
    "fridge": "switch",
    "refrigerator": "switch",
    "kuehlschrank": "switch",
    "kühlschrank": "switch",
    "steckdose": "switch",
    "schalter": "switch",
}

AREA_SYNONYMS: dict[str, str] = {
    # living room
    "living room": "living_room",
    "lounge": "living_room",
    "sitting room": "living_room",
    "front room": "living_room",
    "main room": "living_room",
    "wohnzimmer": "living_room",
    "wohnraum": "living_room",
    # bedroom
    "master bedroom": "bedroom",
    "main bedroom": "bedroom",
    "bed room": "bedroom",
    "schlafzimmer": "bedroom",
    "schlafraum": "bedroom",
    # bathroom
    "loo": "bathroom",
    "toilet": "bathroom",
    "wc": "bathroom",
    "bath": "bathroom",
    "restroom": "bathroom",
    "badezimmer": "bathroom",
    "bad": "bathroom",
    "duschbad": "bathroom",
    # office / study
    "study": "office",
    "home office": "office",
    "work room": "office",
    "workroom": "office",
    "büro": "office",
    "arbeitszimmer": "office",
    "homeoffice": "office",
    # kitchen
    "kitchenette": "kitchen",
    "küche": "kitchen",
    "kueche": "kitchen",
    # hallway
    "hallway": "hall",
    "entrance": "hall",
    "foyer": "hall",
    "corridor": "hall",
    "flur": "hall",
    "diele": "hall",
    "eingang": "hall",
    "korridor": "hall",
    # dining room
    "dining room": "dining_room",
    "dining_room": "dining_room",
    "esszimmer": "dining_room",
    "essbereich": "dining_room",
    # garage
    "garage": "garage",
    # cellar / basement
    "cellar": "basement",
    "keller": "basement",
    # garden / outdoor
    "garden": "garden",
    "yard": "garden",
    "backyard": "garden",
    "outside": "garden",
    "outdoor": "garden",
    "patio": "garden",
    "garten": "garden",
    "terrasse": "garden",
    "terrace": "garden",
    "balcony": "balcony",
    "balkon": "balcony",
    # children's room
    "kinderzimmer": "kids_room",
    "kids room": "kids_room",
    "nursery": "kids_room",
    # guest room
    "guest room": "guest_room",
    "gästezimmer": "guest_room",
    "gaestezimmer": "guest_room",
    # attic / loft
    "attic": "attic",
    "loft": "attic",
    "dachboden": "attic",
    "dachgeschoss": "attic",
    "speicher": "attic",
}

ACTION_SYNONYMS: dict[str, str] = {
    # turn on
    "switch on": "turn on",
    "put on": "turn on",
    "activate": "turn on",
    "enable": "turn on",
    "anschalten": "turn on",
    "einschalten": "turn on",
    "an machen": "turn on",
    "anmachen": "turn on",
    # turn off
    "switch off": "turn off",
    "put off": "turn off",
    "kill": "turn off",
    "cut": "turn off",
    "deactivate": "turn off",
    "disable": "turn off",
    "ausschalten": "turn off",
    "abschalten": "turn off",
    "aus machen": "turn off",
    "ausmachen": "turn off",
}


def normalize_lookup(text: str) -> str:
    value = (text or "").lower()
    replacements = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}
    for source, target in replacements.items():
        value = value.replace(source, target)
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def _apply_action_synonyms(text: str) -> str:
    lowered = text.lower()
    for alias, canonical in sorted(ACTION_SYNONYMS.items(), key=lambda x: -len(x[0])):
        lowered = lowered.replace(alias, canonical)
    return lowered


def _normalize_area(raw: str) -> str:
    lowered = raw.strip().lower()
    lowered = lowered.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    for alias, canonical in sorted(AREA_SYNONYMS.items(), key=lambda x: -len(x[0])):
        alias_normalized = alias.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
        if lowered == alias_normalized:
            return canonical
    return re.sub(r"[^a-z0-9]+", "_", lowered).strip("_")


def _normalize_device_kind(raw: str) -> str | None:
    lowered = raw.strip().lower()
    lowered = lowered.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    for alias, canonical in sorted(DEVICE_KIND_SYNONYMS.items(), key=lambda x: -len(x[0])):
        alias_normalized = alias.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
        if lowered == alias_normalized:
            return canonical
    return None


# Area extraction: match a single area word after a preposition.
# German areas are single compound words (Wohnzimmer, Schlafzimmer, Küche).
# English multi-word areas (living room, home office) are looked up via synonyms.
_AREA_WORD_PAT = r"[a-zA-ZäöüÄÖÜß][a-zA-ZäöüÄÖÜß0-9-]+"

# Two-word area phrases only for known English combos
_AREA_MULTI_WORDS = "|".join(
    re.escape(k) for k in sorted(AREA_SYNONYMS.keys(), key=len, reverse=True) if " " in k
)

_AREA_PREP_MULTIWORD = re.compile(
    rf"\b(?:in(?:\s+(?:der|dem|the))?|im|in\s+the|on\s+the)\s+({_AREA_MULTI_WORDS})\b",
    re.IGNORECASE,
)

_AREA_PREP_SINGLE = re.compile(
    rf"\b(?:in(?:\s+(?:der|dem|the))?|im|in\s+the|on\s+the)\s+({_AREA_WORD_PAT})\b",
    re.IGNORECASE,
)


# Canonical area words that can appear as compound noun prefixes without a preposition.
# E.g. "bedroom light", "kitchen thermostat", "turn off bedroom lamp"
_CANONICAL_AREA_PREFIXES: tuple[str, ...] = tuple(
    sorted(
        set(AREA_SYNONYMS.keys()) | {
            "bedroom", "bathroom", "kitchen", "office", "hallway", "hall",
            "garage", "basement", "garden", "balcony", "attic",
            "living_room", "dining_room",
        },
        key=len,
        reverse=True,
    )
)

_AREA_COMPOUND_PAT = re.compile(
    r"\b("
    + "|".join(re.escape(k) for k in _CANONICAL_AREA_PREFIXES)
    + r")\s+\w",
    re.IGNORECASE,
)


def _extract_area_from_text(text: str) -> str | None:
    m = _AREA_PREP_MULTIWORD.search(text) or _AREA_PREP_SINGLE.search(text)
    if m:
        raw = m.group(1).strip()
        if raw and len(raw) <= 40:
            normalized = _normalize_area(raw)
            if normalized:
                return normalized
    # Compound noun pattern: "bedroom light", "kitchen thermostat"
    m2 = _AREA_COMPOUND_PAT.search(text)
    if m2:
        raw = m2.group(1).strip()
        if raw and len(raw) <= 40:
            normalized = _normalize_area(raw)
            if normalized:
                return normalized
    return None


_DEVICE_KIND_TERMS = re.compile(
    r"\b("
    + "|".join(re.escape(k) for k in sorted(DEVICE_KIND_SYNONYMS.keys(), key=len, reverse=True))
    + r")\b",
    re.IGNORECASE,
)


def _extract_device_kind_from_text(text: str) -> str | None:
    m = _DEVICE_KIND_TERMS.search(text)
    if not m:
        return None
    return _normalize_device_kind(m.group(1))


_QUANTIFIER_PATTERN = re.compile(
    r"\b(all|every|each|both|alle|jeden|jede|jedes|sämtliche)\b",
    re.IGNORECASE,
)


def _has_quantifier(text: str) -> bool:
    return bool(_QUANTIFIER_PATTERN.search(text))


_TIME_TOKENS_DE = frozenset((
    "heute", "morgen", "übermorgen", "uebermorgen",
    "montag", "dienstag", "mittwoch", "donnerstag", "freitag", "samstag", "sonntag",
    "morgens", "mittag", "mittags", "nachmittags", "abends", "früh", "frueh",
))

_TIME_TOKENS_EN = frozenset((
    "tomorrow", "today", "yesterday", "overmorrow",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "noon", "midnight", "morning", "afternoon", "evening", "night",
    "next week", "this week",
))


def _has_time_reference(text: str) -> bool:
    lowered = text.lower()
    return bool(
        re.search(r"\b(\d{1,2})[:.](\d{2})\b", lowered)
        or re.search(r"\b(\d{1,2})[./-](\d{1,2})(?:[./-](\d{2,4}))?\b", lowered)
        or re.search(r"\bat\s+\d{1,2}\b", lowered)
        or re.search(r"\bum\s+\d{1,2}\b", lowered)
        or re.search(r"\bin\s+\d+\s+(?:minutes?|hours?|minuten?|stunden?)\b", lowered)
        or any(token in lowered for token in _TIME_TOKENS_DE)
        or any(token in lowered for token in _TIME_TOKENS_EN)
    )


_WEEKDAY_MAP: dict[str, int] = {
    "montag": 0, "monday": 0,
    "dienstag": 1, "tuesday": 1,
    "mittwoch": 2, "wednesday": 2,
    "donnerstag": 3, "thursday": 3,
    "freitag": 4, "friday": 4,
    "samstag": 5, "saturday": 5,
    "sonntag": 6, "sunday": 6,
}


def _parse_target_day(lowered: str, now: datetime) -> date:
    if "übermorgen" in lowered or "uebermorgen" in lowered or "overmorrow" in lowered:
        return (now + timedelta(days=2)).date()
    if "tomorrow" in lowered:
        return (now + timedelta(days=1)).date()
    morgen_match = re.search(r"\bmorgen\b", lowered)
    if morgen_match:
        return (now + timedelta(days=1)).date()
    if "today" in lowered or "heute" in lowered:
        return now.date()
    weekday_match = next((value for key, value in _WEEKDAY_MAP.items() if key in lowered), None)
    if weekday_match is not None:
        delta = (weekday_match - now.weekday()) % 7
        if delta == 0:
            delta = 7
        return (now + timedelta(days=delta)).date()
    absolute_match = re.search(r"\b(\d{1,2})[./-](\d{1,2})(?:[./-](\d{2,4}))?\b", lowered)
    if absolute_match:
        day = int(absolute_match.group(1))
        month = int(absolute_match.group(2))
        year_raw = absolute_match.group(3)
        year = int(year_raw) if year_raw else now.year
        if year < 100:
            year += 2000
        return datetime(year, month, day, tzinfo=timezone.utc).date()
    return now.date()


def _parse_target_time(lowered: str) -> tuple[int, int]:
    hhmm_match = re.search(r"\b(\d{1,2})[:.](\d{2})\b", lowered)
    if hhmm_match:
        return int(hhmm_match.group(1)), int(hhmm_match.group(2))
    bare_hour_match = re.search(r"\b(?:at|um)\s+(\d{1,2})\b", lowered)
    if bare_hour_match:
        return int(bare_hour_match.group(1)), 0
    if "midnight" in lowered:
        return 0, 0
    if "nachmittags" in lowered or "afternoon" in lowered:
        return 15, 0
    if "mittags" in lowered or re.search(r"\bnoon\b", lowered) or "mittag" in lowered:
        return 12, 0
    if "abends" in lowered or "abend" in lowered or "evening" in lowered or "night" in lowered:
        return 19, 0
    if "morgens" in lowered or "früh" in lowered or "frueh" in lowered or "morning" in lowered:
        return 8, 0
    return 9, 0


def parse_iso_from_text(text: str) -> str:
    lowered = text.lower()
    now = datetime.now(timezone.utc)
    target_day = _parse_target_day(lowered, now)
    hour, minute = _parse_target_time(lowered)
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


_CONFIDENCE_EXACT = 1.0
_CONFIDENCE_SYNONYM_KIND = 0.85
_CONFIDENCE_AREA_KIND = 0.80
_CONFIDENCE_PARTIAL = 0.65
_CONFIDENCE_THRESHOLD_EXECUTE = 0.60
_CONFIDENCE_THRESHOLD_WARN = 0.80


def _entities_for_context(ctx: HomeAssistantChatContext) -> list[dict[str, object]]:
    return ctx.service.list_managed_entities(user_id=ctx.user_id, role=ctx.role).get("entities") or []


def _area_matches(entity_area: str, target_area: str) -> bool:
    if not entity_area or not target_area:
        return False
    e = _normalize_area(entity_area)
    t = _normalize_area(target_area)
    return e == t or e.replace("_", "") == t.replace("_", "")


def _score_entity_match(
    entity: dict[str, object],
    normalized_text: str,
    target_area: str | None,
    target_kind: str | None,
) -> float:
    label = normalize_lookup(str(entity.get("label") or ""))
    entity_area = str(entity.get("area") or "").strip()
    entity_kind = str(entity.get("kind") or "").strip().lower()

    label_hit = bool(label and label in normalized_text)
    area_hit = _area_matches(entity_area, target_area) if target_area else False
    kind_hit = (entity_kind == target_kind) if target_kind else False

    if label_hit and area_hit:
        return _CONFIDENCE_EXACT
    if label_hit:
        return _CONFIDENCE_EXACT
    if area_hit and kind_hit:
        return _CONFIDENCE_AREA_KIND
    if kind_hit and not target_area:
        return _CONFIDENCE_SYNONYM_KIND
    return 0.0


def _find_entity_with_confidence(
    ctx: HomeAssistantChatContext,
    target_area: str | None = None,
    target_kind: str | None = None,
) -> tuple[dict[str, object], float] | None:
    entities = _entities_for_context(ctx)
    best: tuple[dict[str, object], float] | None = None
    for entity in entities:
        score = _score_entity_match(entity, ctx.normalized, target_area, target_kind)
        if score <= 0.0:
            continue
        if best is None or score > best[1]:
            best = (entity, score)
    return best


def _find_entity_by_text(ctx: HomeAssistantChatContext) -> dict[str, object] | None:
    result = _find_entity_with_confidence(ctx)
    if result is None:
        return None
    entity, score = result
    if score < _CONFIDENCE_THRESHOLD_EXECUTE:
        logger.info("HA intent not matched (confidence %.2f < threshold): %s", score, ctx.text)
        return None
    return entity


def _find_entities_by_area_kind(
    ctx: HomeAssistantChatContext,
    target_area: str | None,
    target_kind: str | None,
) -> list[dict[str, object]]:
    entities = _entities_for_context(ctx)
    matched = []
    for entity in entities:
        entity_area = str(entity.get("area") or "").strip()
        entity_kind = str(entity.get("kind") or "").strip().lower()
        if target_area and not _area_matches(entity_area, target_area):
            continue
        if target_kind and entity_kind != target_kind:
            continue
        matched.append(entity)
    return matched


def _device_action_from_text(normalized: str, kind: str) -> str | None:
    actions = {str(item.get("action") or "") for item in DEVICE_ACTION_PROFILES.get(kind, {}).get("actions", [])}
    # German split verb: 'schalte X ein' (turn on)
    if "turn_on" in actions and re.search(r"\bschalte\b.{0,60}\bein\b", normalized):
        return "turn_on"
    candidates = (
        ("turn_off", ("turn off", "ausschalt", " aus", "aus ", "deaktivier", "abschalten", "ausmachen")),
        ("turn_on", ("turn on", "einschalt", " an", "an ", "aktivier", "anschalten", "anmachen")),
        ("set_brightness", ("dim", "brighten", "brightness", "helligkeit", "dimmen", "aufhellen", "set brightness", "set to", "auf")),
        ("set_temperature", ("set temperature", "set temp", "temperatur", "grad", "degrees")),
        ("set_color_temp", ("color temp", "colour temp", "farbtemperatur", "warmweis", "kaltweis", "warm white", "cold white")),
        ("unlock", ("entriegel", "entriegl", "entsperr", " unlock", "oeffne schloss")),
        ("lock", ("verriegel", "sperr", " lock")),
        ("open", ("oeffne", "aufmach")),
        ("close", ("schliess", "zumach")),
        ("arm", (" scharf", " arm", "aktivieren alarm")),
        ("disarm", ("entschaerf", " disarm", "deaktivieren alarm", "unscharf")),
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


def _resolve_area_scoped_action(ctx: HomeAssistantChatContext) -> dict[str, object] | None:
    normalized = ctx.normalized
    action_normalized = _apply_action_synonyms(normalized)
    desired_action = _action_from_normalized(action_normalized)
    if not desired_action:
        return None
    target_area = _extract_area_from_text(ctx.text)
    target_kind = _extract_device_kind_from_text(ctx.text)
    if not target_area and not target_kind:
        return None
    if not target_area and not _has_quantifier(ctx.text):
        return None
    entities = _find_entities_by_area_kind(ctx, target_area, target_kind)
    if not entities:
        return None
    if len(entities) == 1:
        entity = entities[0]
        kind = str(entity.get("kind") or "").strip().lower()
        remote_actions = {"unlock", "lock", "open", "close", "arm", "disarm", "record", "stream"}
        return {
            "action": "entity_action",
            "params": {
                "entity_id": str(entity.get("entity_id") or ""),
                "entity_label": str(entity.get("label") or ""),
                "action": desired_action,
                "value": _build_action_value(desired_action),
                "remote": desired_action in remote_actions,
                "confidence": _CONFIDENCE_AREA_KIND,
            },
        }
    entity_ids = [str(e.get("entity_id") or "") for e in entities]
    entity_labels = [str(e.get("label") or "") for e in entities]
    area_label = target_area.replace("_", " ") if target_area else ""
    kind_label = target_kind or ""
    return {
        "action": "area_entity_action",
        "params": {
            "entity_ids": entity_ids,
            "entity_labels": entity_labels,
            "action": desired_action,
            "value": _build_action_value(desired_action),
            "area": area_label,
            "kind": kind_label,
            "confidence": _CONFIDENCE_AREA_KIND,
        },
    }


def _action_from_normalized(text: str) -> str | None:
    # German split verb: 'schalte X ein' (turn on) — must be checked before the candidate list
    # because ' ein' would otherwise not match any turn_on variant.
    if re.search(r"\bschalte\b.{0,60}\bein\b", text):
        return "turn_on"
    candidates = (
        ("turn_off", ("turn off", "ausschalten", "ausmachen", "abschalten", " aus", "aus ", "deaktivier", " off")),
        ("turn_on", ("turn on", "einschalten", "anschalten", "anmachen", " an ", " an", "aktivier", " on")),
        ("set_brightness", ("dim", "brighten", "brightness", "helligkeit", "dimmen", "aufhellen")),
        ("set_temperature", ("set temperature", "set temp", "temperatur", "degrees", "grad", "set to", "setze auf")),
        ("set_color_temp", ("color temp", "colour temp", "farbtemperatur")),
        ("unlock", ("entriegel", "entriegl", "entsperr", " unlock", "oeffne schloss")),
        ("lock", ("verriegel", "sperr", " lock")),
        ("open", ("oeffne", "aufmach", "open ")),
        ("close", ("schliess", "zumach", "close ")),
    )
    for action, variants in candidates:
        if any(variant in text for variant in variants):
            return action
    return None


def _resolve_temperature_action(ctx: HomeAssistantChatContext) -> dict[str, object] | None:
    normalized = ctx.normalized
    temp_match = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:grad|degrees?|°|celsius|°c)?", normalized)
    if not temp_match:
        return None
    if not any(w in normalized for w in ("temperatur", "grad", "degrees", "set", "einstell", "setze", "celsius")):
        return None
    temperature = float(temp_match.group(1).replace(",", "."))
    if temperature < 5 or temperature > 35:
        return None
    target_area = _extract_area_from_text(ctx.text)
    target_kind = "climate"
    entities = _find_entities_by_area_kind(ctx, target_area, target_kind)
    if not entities:
        result = _find_entity_with_confidence(ctx, target_area, target_kind)
        if result is None:
            return None
        entity, score = result
        if score < _CONFIDENCE_THRESHOLD_EXECUTE:
            logger.info("HA intent not matched, falling through to LLM: %s", ctx.text)
            return None
        entities = [entity]
    entity = entities[0]
    return {
        "action": "entity_action",
        "params": {
            "entity_id": str(entity.get("entity_id") or ""),
            "entity_label": str(entity.get("label") or ""),
            "action": "set_temperature",
            "value": temperature,
            "remote": False,
            "confidence": _CONFIDENCE_AREA_KIND if target_area else _CONFIDENCE_SYNONYM_KIND,
        },
    }


def _resolve_brightness_action(ctx: HomeAssistantChatContext) -> dict[str, object] | None:
    normalized = ctx.normalized
    if not any(w in normalized for w in ("dim", "brighten", "brightness", "helligkeit", "dimmen", "aufhellen", "prozent", "percent")):
        return None
    pct_match = re.search(r"(\d{1,3})\s*(?:%|percent|prozent)", normalized)
    if not pct_match:
        return None
    brightness_pct = int(pct_match.group(1))
    if brightness_pct < 0 or brightness_pct > 100:
        return None
    target_area = _extract_area_from_text(ctx.text)
    target_kind = _extract_device_kind_from_text(ctx.text)
    if target_kind is None:
        target_kind = "light"
    entities = _find_entities_by_area_kind(ctx, target_area, target_kind)
    if not entities:
        result = _find_entity_with_confidence(ctx, target_area, target_kind)
        if result is None:
            logger.info("HA intent not matched, falling through to LLM: %s", ctx.text)
            return None
        entity, score = result
        if score < _CONFIDENCE_THRESHOLD_EXECUTE:
            logger.info("HA intent not matched (confidence %.2f), falling through to LLM: %s", score, ctx.text)
            return None
        entities = [entity]
    if len(entities) == 1:
        entity = entities[0]
        return {
            "action": "entity_action",
            "params": {
                "entity_id": str(entity.get("entity_id") or ""),
                "entity_label": str(entity.get("label") or ""),
                "action": "set_brightness",
                "value": brightness_pct,
                "remote": False,
                "confidence": _CONFIDENCE_AREA_KIND if target_area else _CONFIDENCE_SYNONYM_KIND,
            },
        }
    entity_ids = [str(e.get("entity_id") or "") for e in entities]
    entity_labels = [str(e.get("label") or "") for e in entities]
    area_label = target_area.replace("_", " ") if target_area else ""
    return {
        "action": "area_entity_action",
        "params": {
            "entity_ids": entity_ids,
            "entity_labels": entity_labels,
            "action": "set_brightness",
            "value": brightness_pct,
            "area": area_label,
            "kind": target_kind,
            "confidence": _CONFIDENCE_AREA_KIND,
        },
    }


def _resolve_entity_action(ctx: HomeAssistantChatContext) -> dict[str, object] | None:
    normalized = ctx.normalized
    action_normalized = _apply_action_synonyms(normalized)
    if not any(
        word in action_normalized
        for word in (
            "turn on",
            "turn off",
            " an",
            " aus",
            " on",
            " off",
            " einschalten",
            " ausschalten",
            " schalte ",
            "schalte",
            " mach ",
            "mache",
            "oeff",
            "schliess",
            "verriegel",
            "entriegel",
            "entriegl",
            "entsperr",
            "alarm",
            "kamera",
            "aufnahme",
            "stream",
        )
    ):
        return None
    target_area = _extract_area_from_text(ctx.text)
    target_kind = _extract_device_kind_from_text(ctx.text)
    result = _find_entity_with_confidence(ctx, target_area, target_kind)
    if result is None:
        logger.info("HA intent not matched, falling through to LLM: %s", ctx.text)
        return None
    target_entity, confidence = result
    if confidence < _CONFIDENCE_THRESHOLD_EXECUTE:
        logger.info("HA intent not matched (confidence %.2f), falling through to LLM: %s", confidence, ctx.text)
        return None
    if confidence < _CONFIDENCE_THRESHOLD_WARN:
        logger.warning("HA intent matched with low confidence %.2f for: %s", confidence, ctx.text)
    kind = str(target_entity.get("kind") or "").strip().lower()
    desired_action = _device_action_from_text(action_normalized, kind)
    if not desired_action:
        return {
            "action": "missing_entity_action_details",
            "params": {
                "entity_id": str(target_entity.get("entity_id") or ""),
                "entity_label": str(target_entity.get("label") or ""),
                "kind": kind,
                "confidence": confidence,
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
            "confidence": confidence,
        },
    }


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
    _resolve_temperature_action,
    _resolve_brightness_action,
    _resolve_area_scoped_action,
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
    logger.debug("HA intent not matched, falling through to LLM: %s", text)
    return None
