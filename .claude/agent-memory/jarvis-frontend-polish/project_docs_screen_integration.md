---
name: project-docs-screen-integration
description: How DocsScreen fetches and displays live integration status (RAG + HA) on mount, including status summary bar
metadata:
  type: project
---

**Feature:** DocsScreen fetches `GET /health`, `GET /rag/status`, and `GET /home-assistant/health` concurrently on mount using `Promise.allSettled`, shows a live status summary bar at the top of every section, and allows manual refresh.

**Pattern used:**
- `useState<RagStatus | null>(null)` + `useState<boolean>(false)` for error per integration
- `useCallback`-wrapped `fetchStatuses()` uses `Promise.allSettled` for all 3 endpoints — never throws
- `useEffect(() => { fetchStatuses(); }, [fetchStatuses])` fires on mount via stable useCallback dep
- `resolveRagState()` and `resolveHaState()` are pure functions mapping (data|null, error:bool) → `IntegrationState`
- `IntegrationBadge` renders per-integration state as color pill (loading/active/inactive/unknown)
- `StatusSummaryBar` component renders at top of content area on ALL sections — shows 4 chips + last-updated timestamp + refresh button (↺)
- `StatusChip` component maps ok/warn/error/loading to J.success/J.warn/J.error/J.textMuted colors
- `ragDocCount()` helper sums all counts from RagStatus.counts record
- `formatTimeAgo()` formats millisecond timestamp to "just now / Xs ago / Xm ago"
- Timer in StatusSummaryBar re-renders every 10s to keep "Updated Xs ago" fresh

**Graceful degradation:**
- All 3 endpoints run via Promise.allSettled — individual failures don't abort the others
- Failed endpoints: show 'unknown' / 'error' state, never crash component
- JARVIS Core chip goes error (red ✗) if /health fails, shows green ✓ Online if up
- Voice is always shown as "Ready" (no backend check needed for TTS/STT)

**Key invariant:** `refreshing` is set to true at start of fetchStatuses and false only after allSettled resolves — prevents double-click races.

**Auth note:** `/health` does NOT need auth (no `includeUser`), but `apiRequest` with no options works fine for it. RAG and HA endpoints use `{ includeUser: true }` inside their wrapper functions.
