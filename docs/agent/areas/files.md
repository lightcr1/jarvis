# Bereich: Files / Workspace

- Zweck: Datei-Upload/Download, Shares, Pfadsicherheit.
- Kern: `jarvis/files/` — `store.py`, `service.py`, `path_safety.py`,
  `share_store.py`, `link_share_store.py`, `permissions.py`, `chat_helpers.py`.
- API: `jarvis/api_files.py`; Workspace: `jarvis/workspace/store.py`,
  `jarvis/api_workspace.py`.
- Sicherheit: Pfade immer über `path_safety.py` prüfen (Traversal/Scope),
  Freigaben serverseitig in `permissions.py`.
- Tests: `tests/test_files.py`, `tests/test_workspace.py`.
- Geschützt: `jarvis/permission*.py` nur als Vorschlags-PR.
