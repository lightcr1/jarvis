---
name: area-synonym-gaps
description: Missing area synonyms discovered and added to AREA_SYNONYMS in chat_intents.py
metadata:
  type: project
---

The following synonyms were added in the V38 hardening pass:

- "main room" → living_room
- "bed room" → bedroom (two-word variant)
- "bath" → bathroom
- "restroom" → bathroom
- "work room" → office
- "workroom" → office
- "foyer" → hall
- "corridor" → hall
- "patio" → garden
- "outdoor" → garden
- "outside" → garden
- "kitchenette" → kitchen
- "attic", "loft", "dachboden", "dachgeschoss", "speicher" → attic

Previously existing coverage: living_room, bedroom, bathroom, office, kitchen, hall, dining_room, garage, basement, garden, balcony, kids_room, guest_room.

**Why:** Area routing is fragile if synonyms are missing — entity lookups fail silently and fall through to LLM with no useful response.

**How to apply:** When adding new room types, always add both German and English variants. Single-word German compounds (Dachboden, Wohnzimmer, Schlafzimmer) must be in the table; the regex extracts them as single words and _normalize_area handles umlaut folding before lookup. "patio" requires "in the patio" not "on the patio" to trigger area extraction — the preposition pattern only matches in/im/in der/in dem.
</content>
