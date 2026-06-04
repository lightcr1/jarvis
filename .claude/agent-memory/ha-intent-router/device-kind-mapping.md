---
name: device-kind-mapping
description: HA entity kind values used in JARVIS — media entities use "media" not "media_player"
metadata:
  type: project
---

JARVIS uses short kind strings that differ from raw Home Assistant domain names:

| JARVIS kind | HA domain | Synonyms (→ JARVIS kind) |
|---|---|---|
| "light" | light | lamp, lamps, licht, lichter, lampe, lampen, bulb, bulbs |
| "climate" | climate | ac, aircon, air con, klimaanlage, klima, heizung, thermostat |
| "media" | media_player | tv, telly, television, fernseher, speaker, lautsprecher |
| "cover" | cover | blinds, shutter, rollo, jalousie |
| "lock" | lock | door lock, türschloss |
| "switch" | switch | fridge, plug, socket, steckdose |
| "camera" | camera | kamera |
| "alarm" | alarm_control_panel | alarm |
| "garage_door" | cover (garage) | garage door |
| "sensor" | sensor | (read-only, no actions) |

**Why:** DEVICE_ACTION_PROFILES in service.py uses these short kinds as keys. The synonym table in chat_intents.py must map to these exact strings.

**How to apply:** When adding new device synonyms, check that the target canonical kind exists as a key in DEVICE_ACTION_PROFILES. Never use "media_player" — always "media".
</content>
