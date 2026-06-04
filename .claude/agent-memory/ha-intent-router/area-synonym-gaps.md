---
name: area-synonym-gaps
description: Missing area synonyms discovered and added to AREA_SYNONYMS in chat_intents.py
metadata:
  type: project
---

Added attic/loft/Dachboden mapping ("attic", "loft", "dachboden", "dachgeschoss", "speicher" → "attic") — these were missing from the original synonym table despite the spec requiring Dachboden=attic.

The AREA_SYNONYMS table in chat_intents.py already had good coverage for: living_room, bedroom, bathroom, office, kitchen, hall, dining_room, garage, basement, garden, balcony, kids_room, guest_room.

**Why:** The task spec explicitly listed Dachboden=attic as a required synonym. Area routing is fragile if synonyms are missing — entity lookups fail silently.

**How to apply:** When adding new room types, always add both German and English variants. Single-word German compounds (Dachboden, Wohnzimmer, Schlafzimmer) must be in the table; the regex extracts them as single words and _normalize_area handles umlaut folding before lookup.
</content>
