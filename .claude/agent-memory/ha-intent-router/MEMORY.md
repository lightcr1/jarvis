# HA Intent Router Memory Index

- [Area Synonym Gaps](area-synonym-gaps.md) — Full list of area synonyms added; patio requires "in the patio" not "on the patio"
- [Datetime Parity Gaps](datetime-parity.md) — English datetime tokens missing from _has_time_reference; German "um X" fixed
- [Silent Fallback Pattern](silent-fallback.md) — Final return None must always have a logger.debug() before it
- [Device Kind Mapping](device-kind-mapping.md) — Canonical kind values; "switch" noun excluded (ambiguous with verb); fan/lock/cover expanded
- [German Split Verb Pattern](german-split-verb-pattern.md) — "schalte X ein" requires regex; simple substring checks miss it
</content>
</invoke>