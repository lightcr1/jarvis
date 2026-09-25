# Plugins (Entwurf, Plan 5.2)

J.A.R.V.I.S. kann Fähigkeiten als **Plugin** nachliefern, statt geschützte
Kernmodule zu ändern. Ein Plugin liegt in `jarvis/plugins/<name>/`:

```
jarvis/plugins/<name>/
├── manifest.json   # Pflicht: Name, Version, Capabilities, Risiko, Zugriffe
├── tool.py         # (folgt) Implementierung der deklarierten Tool(s)
└── tests/          # (folgt) Tests des Plugins
```

## Manifest

```json
{
  "name": "backup_reporter",
  "version": "0.1.0",
  "description": "Meldet den Status der Backups.",
  "capabilities": ["status.read"],
  "tier": "T0",
  "credentials": ["backup_api"],
  "network_targets": ["10.0.0.5:22"]
}
```

| Feld | Pflicht | Bedeutung |
|---|---|---|
| `name` | ja | nur `a-z`, `0-9`, `_` (kein Pfad, keine Punkte) |
| `version` | ja | freie Versionskennung |
| `capabilities` | ja | nicht-leere Liste aus der Capability-Registry |
| `tier` | ja | Risikostufe `T0`–`T3` (**Vorschlag**, scharf schaltet der Besitzer) |
| `credentials` | ja | **Referenzen** auf Credentials (keine Werte!) |
| `network_targets` | ja | erlaubte Egress-Ziele (über den Allowlist-Proxy) |
| `description` | nein | Kurzbeschreibung |

## Regeln des Loaders (`jarvis/plugins.py`)

- Der Loader liest **nur** das Manifest und führt **keinen** Plugin-Code aus.
- Ein Plugin darf sein Risiko **nie unter** die Capability-Registry senken:
  `tier` muss ≥ der Registry-Stufe jeder Capability sein.
- Unbekannte (neue) Capabilities sind mindestens **T2** (fail-safe).
- `credentials` und `network_targets` sind Listen von Referenzen; verschachtelte
  Werte (echte Secrets) werden abgelehnt.
- Der Plugin-Code bekommt **nur** die deklarierten Credentials und Netzziele.

## Status / nächste Schritte

- Umgesetzt: Manifest-Prüfung + Tests (`tests/test_plugins.py`).
- Offen (Plan 5.1/5.3): Tool-Code laden und als Tool registrieren,
  „Werkzeug fehlt“ → Agent-Aufgabe, und `jarvis.deploy` (T2) mit Health-Check
  und Rollback.
