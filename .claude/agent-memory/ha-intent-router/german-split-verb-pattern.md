---
name: german-split-verb-pattern
description: German separable verb "schalte X ein" (turn on) needs special regex handling — not covered by simple substring checks
metadata:
  type: project
---

German separable verbs split across a sentence: "schalte das Licht ein" (turn on the light) has the prefix "ein" at the end, not attached to "schalte". This means substring checks for "einschalten" or " an" do NOT match.

Fixed in `_action_from_normalized` and `_device_action_from_text` by adding a regex guard before the candidates list:

```python
if re.search(r"\bschalte\b.{0,60}\bein\b", text):
    return "turn_on"
```

"schalte X aus" already worked because the `" aus"` substring check catches it.

**Why:** "schalte das Licht im Wohnzimmer ein" was routing into `_resolve_entity_action` (the "schalte" guard matched), finding the entity correctly, but returning `missing_entity_action_details` because `_device_action_from_text` returned None for the action.

**How to apply:** The same pattern applies to other German split verbs if they're ever needed. Always add both the split-verb regex AND the unsplit form to cover both natural speech patterns. The `{0,60}` bound prevents backtracking across sentence boundaries.

Related: [[datetime-parity]] — German "um X" time pattern also required similar explicit regex addition.
