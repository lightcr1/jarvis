---
name: device-kind-mapping
description: HA entity kind values used in JARVIS — media entities use "media" not "media_player"
metadata:
  type: project
---

JARVIS uses short kind strings that differ from raw Home Assistant domain names:

| JARVIS kind | HA domain | Synonyms (→ JARVIS kind) |
|---|---|---|
| "light" | light | lamp, lamps, licht, lichter, lampe, lampen, bulb, bulbs, lighting, beleuchtung |
| "climate" | climate | ac, aircon, air con, klimaanlage, klima, heizung, thermostat, heat, temperature, temperatur |
| "media" | media_player | tv, telly, television, screen, display, fernseher, speaker, lautsprecher |
| "cover" | cover | blinds, shutter, rollo, jalousie, curtains, curtain, roller blind, vorhang |
| "lock" | lock | lock, door lock, front door, back door, türschloss, schloss, haustür |
| "fan" | fan | fan, ceiling fan, ventilation, ventilator, lüfter |
| "switch" | switch | plug, socket, outlet, fridge, refrigerator, steckdose, schalter (NOT "switch" — ambiguous with action verb) |
| "camera" | camera | kamera |
| "alarm" | alarm_control_panel | alarm |
| "garage_door" | cover (garage) | garage door |
| "sensor" | sensor | (read-only, no actions) |

Note: "switch" as a device noun is intentionally excluded from DEVICE_KIND_SYNONYMS because "switch on/off" are common action phrases. Using it would cause false positives.

**Why:** DEVICE_ACTION_PROFILES in service.py uses these short kinds as keys. The synonym table in chat_intents.py must map to these exact strings.

**How to apply:** When adding new device synonyms, check that the target canonical kind exists as a key in DEVICE_ACTION_PROFILES. Never use "media_player" — always "media". Avoid adding nouns that double as action verbs.
</content>
