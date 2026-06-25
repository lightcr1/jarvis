---
name: compound-noun-area-and-brightness
description: Compound noun area extraction (bedroom light), 'on the' preposition, dim/brighten routing — V39 hardening session
metadata:
  type: project
---

## Compound Noun Area Extraction (V39)

Added `_CANONICAL_AREA_PREFIXES` and `_AREA_COMPOUND_PAT` to `_extract_area_from_text`. Commands like "bedroom light", "kitchen thermostat", "turn off bedroom lamp" now extract the area from the noun compound without requiring a preposition like "in the".

The pattern matches area words appearing immediately before another word. If a preposition pattern matches, it takes priority.

## 'on the' Preposition for Outdoor Areas (V39)

Extended `_AREA_PREP_MULTIWORD` and `_AREA_PREP_SINGLE` to include `on\s+the`. "lights on the patio", "lights on the balcony" now correctly extract area.

The existing test `test_extract_area_patio` was updated from `None` to `"garden"` — it was a regression test that became outdated once 'on the' was supported.

## Dim/Brighten/Brightness Routing (V39)

Added `set_brightness` and `set_color_temp` actions to both `_device_action_from_text` and `_action_from_normalized`. Added `_resolve_brightness_action` resolver (placed before `_resolve_area_scoped_action` in RESOLVERS).

`_resolve_brightness_action` requires BOTH a dim/brighten keyword AND a percentage value `(\d{1,3})\s*(?:%|percent|prozent)`. Without a percentage, it skips and falls through.

## English 'close'/'open' in _action_from_normalized (V39)

Only had German `"schliess"/"zumach"` for close and `"oeffne"/"aufmach"` for open. Added `"close "` and `"open "` (with trailing space to avoid substring collisions). "close all blinds", "open the garage" now route correctly.

## jalousien Plural (V39)

Added `"jalousien": "cover"` to DEVICE_KIND_SYNONYMS. German plural form was missing.

## New Tests: 38 tests in 7 classes (V39)

TestCompoundNounAreaExtraction (11), TestCompoundNounAreaRouting (3), TestBrightnessActionRouting (5), TestDimBrightenSynonymExtraction (7), TestAdditionalGermanParity (7), TestMultiDeviceEdgeCases (4), TestConfidenceFallthrough (3).

Total after session: 1516 tests passing (was 1478).
