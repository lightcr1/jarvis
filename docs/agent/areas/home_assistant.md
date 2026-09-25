# Bereich: Home Assistant

- Zweck: Anbindung an Home Assistant (Geräte, Zustände, Dienste/Aktionen).
- Kern: `jarvis/home_assistant/` — `client.py` (HTTP-Client), `service.py`
  (Fassade), `store.py` (SQLite), `discovery.py`, `risk.py` (Risikoklasse),
  `permissions.py`, `models.py`, `chat_intents.py`/`chat_actions.py`.
- API: `jarvis/api_home_assistant.py`; Verdrahtung über `router_dependencies.py`.
- Konvention: gefährliche Aktionen über `risk.py`/`permissions.py` absichern;
  Berechtigungen nie im Prompt, sondern serverseitig durchsetzen.
- Tests: `tests/test_home_assistant_api.py`, `tests/test_home_assistant_*.py`.
- Geschützt: `jarvis/permission*.py`, `jarvis/auth*.py` nur als Vorschlags-PR.
