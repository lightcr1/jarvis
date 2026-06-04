---
name: project-docs-screen-integration
description: How DocsScreen fetches and displays live integration status (RAG + HA) on mount
metadata:
  type: project
---

**Feature:** DocsScreen now fetches `GET /rag/status` and `GET /home-assistant/health` on mount and shows live availability badges.

**Pattern used:**
- `useState<RagStatus | null>(null)` + `useState<boolean>(false)` for error
- Single `useEffect([], [])` fires both fetches in parallel (no await chain)
- `resolveRagState()` and `resolveHaState()` are pure functions that map (data | null, error: bool) → `'loading' | 'active' | 'inactive' | 'unknown'`
- `IntegrationBadge` component renders the state as a color-coded pill using J tokens only
- `SkillsSection` receives `integrations: IntegrationStatuses` prop and shows RA + HA status pills above the skill list
- `HomeAssistantSection` receives `status: IntegrationState` and shows an inline badge + warning banner if inactive

**Graceful degradation:**
- If both endpoints fail: `ragError = true, haError = true` → both show 'unknown' badge (gray) — all skills still shown
- If endpoint is slow: shows 'loading' badge (gray, "checking…") — transitions once data arrives

**Why this approach:** Fetch-on-mount with error state rather than try/catch in useEffect — keeps the component functional even if integrations are down.
