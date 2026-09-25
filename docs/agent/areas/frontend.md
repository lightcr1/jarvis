# Bereich: Frontend (Admin-UI)

- Zweck: React/TypeScript-Admin-Oberfläche.
- Struktur: `frontend/src/routes/admin/pages/` (Seiten),
  `frontend/src/shared/api/admin.ts` (typisierte API-Aufrufe, `apiRequest` mit
  `includeAdmin`), `frontend/src/components/`, `frontend/src/screens/`,
  `frontend/src/features/`, `frontend/src/test/` (Vitest).
- Muster: neue Seite → Component + Eintrag in der Admin-Navigation;
  neue API-Funktion in `shared/api/admin.ts` mit Interface.
- Tests: `cd frontend && npx vitest run <pfad>` (benötigt `node_modules`).
- Styling: `J`-Theme aus `screens/jarvis-shared` (`J.bg2`, `J.border`,
  `J.textMuted`, `J.amber`, …), kein neues CSS-Framework.
- Backend-Anbindung immer über `apiRequest` (kein rohes `fetch`).
