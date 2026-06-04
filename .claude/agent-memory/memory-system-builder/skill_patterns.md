---
name: skill-patterns
description: Ordering rules for memory skills in try_skill(); alias pattern must come before note pattern to avoid false matches
metadata:
  type: project
---

In `assistant_domain.py::try_skill()`, the alias pattern `remember <key> is <value>` must be checked BEFORE the general note pattern `remember(?: that)? <text>`.

**Why:** `try_skill()` lowercases all input (`t = text.strip().lower()`). "remember city is Hamburg" matches both patterns — the note regex is too greedy. If the note pattern fires first, the alias is stored as a freeform note instead of a structured alias.

**Ordering rule:** More-specific patterns always before more-general ones in `try_skill()`.

**Side effect of lowercasing:** Values stored via `try_skill()` are always lowercase because `t` is lowercased before matching. The REST API (`POST /memory/aliases`) preserves original case because it takes the payload directly without lowercasing. Tests should account for this difference.

**How to apply:** Any time a new skill input pattern overlaps with an existing one, put the more specific pattern higher in the `try_skill` function body.
