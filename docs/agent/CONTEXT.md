# jarvis — Agenten-Kontextkarte

Kompakte Repo-Karte. **Ziel ≤ 1500 Tokens.** Details nie komplett lesen —
per `grep -n <begriff> <datei>` oder `sed -n 'a,bp' <datei>` gezielt
aufschlagen. Bereichskarten: `docs/agent/areas/<bereich>.md`.

## Repo-Karte

- `jarvis/` — Python-Backend (FastAPI): API-Router, Stores, Services.
  Einstieg `jarvisappv4.py` (App + Router-Registrierung, **nie komplett lesen**).
- `jarvis/<bereich>/` — fachliche Module: `billing/`, `home_assistant/`,
  `files/`, `tasks/`, `calendar/`, `email/`, `workspace/`, `providers/`.
- `frontend/` — React/TypeScript-Admin-UI (`src/routes/admin/pages`, `src/shared/api`).
- `tests/` — pytest (Backend) und Vitest (Frontend, `frontend/src/test`).
- `scripts/agent/` — Autonomy-Loop, Gateway, Policy, Helfer (`verify.sh`, `find.sh`).
- `docs/` — Doku; `docs/agent/` = Agenten-Kontext; `docs/v2/` = alte Planung.
- `config/`, `deploy/`, `integrations/` — Konfiguration, Deployment, Integrationen.

## Tests gezielt ausführen

```bash
# Nur betroffene Tests, knappe Ausgabe:
scripts/agent/verify.sh jarvis/tasks/store.py
# Voll (nur wenn nötig, langsam):
python3 -m pytest -q
# Frontend:
cd frontend && npx vitest run <pfad>
```

`scripts/agent/verify.sh [pfade…]` bildet geänderte Pfade auf Testdateien ab,
begrenzt die Ausgabe und prüft `check_policy.py`. `scripts/agent/find.sh <begriff>`
durchsucht das Repo kompakt (ohne `node_modules`, `dist`, `.git`).

## Konventionen

- Sprache: Python- und TS-Code englisch, Kommentare/Doku teils deutsch.
- Stores: SQLite mit `build_*_store`/Klassen, Pfade über `*_store_path`/Env.
- API: `jarvis/api_<bereich>.py` mit `build_*_router(deps)`, registriert in
  `jarvisappv4.py`; Admin-Router zusätzlich in `jarvis/api_admin.py`.
- Tests: `tests/test_<bereich>.py`, HTTP über `fastapi.testclient.TestClient`.
- Klein & reversibel ändern; ein Thema = ein Branch/PR (`agent/<kurzname>`).

## Wichtig zu wissen

- Netzwerk im Agent-Container: kein direktes Internet. GitHub/lokale Dienste
  nur über `scripts/agent/jarvis_gateway.py` (typisierter Freigabeworkflow).
- Geschützte Pfade (nur Vorschlag/PR mit Owner-Review): `AGENTS.md`,
  `config/agent-policy.json`, `.github/**`, `deploy/**`, Auth-/Billing-/
  Permission-Module (`jarvis/auth*.py`, `jarvis/*billing*.py`,
  `jarvis/policy_engine.py`, `jarvis/permission*.py`). Siehe
  `scripts/agent/check_policy.py`.
- Keine `.env`-Dateien, Tokens, Runpod-Ressourcen oder produktiven Dienste anfassen.
- Große Dateien **nicht** vollständig lesen: `CLAUDE.md`,
  `docs/v2/planning/EXECUTION_CHECKLIST_V2.md`, `jarvisappv4.py` — nur greppen.

## Wo Details stehen

- Regeln/Identität: `AGENTS.md` · Ziele: `docs/GOALS.md`
- Autonomy: `docs/AUTONOMY_LOOP.md`, `scripts/agent/autonomy_loop.py`
- Projektfreigaben: `docs/AUTONOMY_LOOP.md` (Abschnitt Projektfreigaben)
- Bereichskarten: `docs/agent/areas/autonomy.md`, `home_assistant.md`,
  `billing.md`, `files.md`, `frontend.md`, `voice.md`
