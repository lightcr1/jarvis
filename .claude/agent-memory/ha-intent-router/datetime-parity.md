---
name: datetime-parity
description: English datetime tokens were missing from _has_time_reference and parse_iso_from_text; refactored in V35 hardening
metadata:
  type: project
---

Before the V35 hardening, `_has_time_reference` and `parse_iso_from_text` only handled German datetime expressions. English equivalents were missing:

Missing from `_has_time_reference`:
- "tomorrow", "today", "yesterday"
- English weekdays (monday..sunday)
- "noon", "midnight", "morning", "afternoon", "evening", "night"
- bare hour pattern "at 8"
- duration pattern "in 30 minutes"

Missing from `parse_iso_from_text`:
- "tomorrow" → +1 day (only "morgen" was handled)
- "today" → current day (only "heute")
- English weekdays
- "noon", "midnight", "morning", "afternoon", "evening"
- bare hour "at 8" (only HH:MM was parsed)

**Fix applied (V35):** Extracted `_parse_target_day()` and `_parse_target_time()` helpers, added `_TIME_TOKENS_EN` frozenset, added `_WEEKDAY_MAP` dict with both German and English weekday names, added `\bat\s+\d{1,2}\b` regex for bare hour.

**Fix applied (V38):** Added German "um X" bare hour pattern:
- `_has_time_reference` now checks `\bum\s+\d{1,2}\b` (German "at X o'clock")
- `_parse_target_time` bare_hour_match regex changed from `\bat\s+(\d{1,2})\b` to `\b(?:at|um)\s+(\d{1,2})\b`
- This makes "morgen um 8" parse correctly to 08:00

**Critical ordering bug:** "afternoon" contains "noon" as substring. `_parse_target_time` must check "afternoon" BEFORE "noon", or use `\bnoon\b` word-boundary regex for the noon check.

**morgen/morgens ambiguity:** "morgens" (German morning) contains "morgen" (German tomorrow). Use `\bmorgen\b` word-boundary regex in `_parse_target_day` to avoid false tomorrow matches from "morgens".

**How to apply:** Any time date/time parsing is touched, verify both English and German test cases pass. The parametrized tests in TestParseIsoEnglish and TestGermanTimePatterns cover all patterns.
</content>
