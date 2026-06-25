---
name: project-v39-features
description: 8 frontend features implemented in V39 final batch — patterns, file locations, and implementation notes
metadata:
  type: project
---

All 8 features implemented in `npm run test:run && npm run build` passing state (15 tests, 0 errors).

## Features implemented

1. **Notification badges** — `Badge` component in `jarvis-shared.tsx`; unreadCount in `JarvisApp.tsx` tracked via `prevAlertCount` ref; gated on `notifications_enabled !== false` pref; badge renders on 'services' nav item in both NavRail and BottomNav.

2. **Quick Actions** — `ChatScreen.tsx`: `quickActions` state from `getStoredPreferences().quick_actions ?? ['Briefing', 'System status', 'Weather']`; edit dialog uses `savePreferences`; compact chip strip renders above Composer when messages exist; `consumePendingChatPrefill` called on mount via `pendingPrefillRef` pattern (two-effect pattern avoids ordering issue with `handleSend`).

3. **Morning Briefing settings** — `SettingsScreen.tsx`: new `briefing` panel in `CATS` and `panels`; uses `morning_briefing_enabled` and `morning_briefing_time` prefs; added to save-bar inclusion list.

4. **Chat export (Markdown)** — `serializeChatToMarkdown()` exported from `ChatScreen.tsx`; download button appears in topbar when session is active and has messages; filename `jarvis-chat-{date}.md`.

5. **Ambient status orb** — `metricsToHealthTier()` exported from `OrbScreen.tsx`; polls `getSystemMetrics()` every 30s; maps to `'good'|'warn'|'critical'`; tints orb background gradient via `healthRef` in `OrbCanvas`.

6. **Persona tone** — `Sel` dropdown in `chat` panel of `SettingsScreen.tsx` for `persona_tone` pref with `formal`/`casual` options.

7. **Keyboard shortcuts** — Global `keydown` in `JarvisApp.tsx`: Cmd/Ctrl+K opens `CommandPalette` overlay; `?` opens `ShortcutsOverlay`; Escape closes both. `CommandPalette` lists nav screens + quick_actions; selecting an action uses `setPendingChatPrefill` + navigate to chat.

8. **PWA** — `public_static/manifest.json` updated (theme #f59e0b, amber icons); `public_static/icons/icon-{192,512}.png` created (minimal valid amber PNGs); `public_static/sw.js` added (network-first, skips streaming/WS routes); registered in `main.tsx` via `navigator.serviceWorker.register`.

## Key patterns discovered

- `publicDir` in `vite.config.ts` points to `public_static/` NOT `public/` — all static assets go there.
- Icon components (`IconBell`, etc.) only accept `{ size?: number }` — pass `color` via wrapping `<span style={{ color: ... }}>`.
- `handleSend` is a `const` defined after `useEffect`, but effects only run post-render so it's safe; used `pendingPrefillRef` as a bridge.
- The drain effect for pendingPrefillRef is placed AFTER `handleSend` is defined to satisfy TypeScript.

## Test file

`frontend/src/shared/api/features.test.ts` — 10 tests for `serializeChatToMarkdown` and `metricsToHealthTier`.
