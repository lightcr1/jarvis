# Bereich: Autonomy-Loop

- Zweck: while der Runpod-Pod läuft, startet der Loop OpenHands-Runden
  (Engineering/Ideen), pausiert bei Besitzeraktivität, schließt per Wrapup ab.
- Kern: `scripts/agent/autonomy_loop.py` (installierte Kopie läuft per Cron,
  nicht das Repo). Doku `docs/AUTONOMY_LOOP.md`.
- Konfiguration: `DEFAULT_CONFIG` im Loop, überschreibbar per
  `autonomy-loop.env` (`AUTONOMY_LOOP_ENV`) und Prozess-Umgebung.
- Policy/Freigaben: `scripts/agent/check_policy.py`,
  `scripts/agent/jarvis_gateway.py`, `config/agent-policy.json`.
- Admin/UI: `jarvis/api_agent_monitor.py`, `jarvis/agent_monitor.py`,
  `frontend/src/routes/admin/pages/AgentMonitorPage.tsx`,
  `frontend/src/routes/admin/pages/AutonomyPage.tsx`.
- Store: `jarvis/autonomy_store.py`, Endpunkte `jarvis/api_autonomy.py`.
- Tests: `tests/test_autonomy_loop.py`, `tests/test_agent_monitor.py`,
  `tests/test_agent_policy.py`, `tests/test_agent_actions.py`,
  `tests/test_agent_grants.py`, `tests/test_autonomy_store.py`.
- Regeln: nie Pods starten/verändern, keine `.env`/Tokens anfassen,
  geschützte Pfade nur als Vorschlags-PR.
