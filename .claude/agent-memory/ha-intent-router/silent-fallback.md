---
name: silent-fallback
description: Contract for HA intent fallback — final return None must log at DEBUG level
metadata:
  type: feedback
---

The contract for `execute_home_assistant_chat_intent()`: if no resolver handles the input, it must return `None` AND log at DEBUG level so the caller (`try_skill()`) knows to fall through to RAG/LLM.

Before V35 hardening the final `return None` was silent — no logging.

Fixed by adding `logger.debug("HA intent not matched, falling through to LLM: %s", text)` immediately before the final `return None` in `execute_home_assistant_chat_intent`.

**Why:** Silent failures make debugging routing issues very hard. Individual resolvers already log at INFO/WARNING when they reject due to low confidence — the final fallback should also be visible.

**How to apply:** Any time a new early-return `None` path is added in `execute_home_assistant_chat_intent`, add a debug log. Resolver functions (`_resolve_*`) should log at INFO when they reject due to confidence threshold, not DEBUG (they're more specific rejections).
</content>
