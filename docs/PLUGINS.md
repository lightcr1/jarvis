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

- Umgesetzt: Manifest-Prüfung (`parse_manifest`/`load_plugins`) + Tests.
- Umgesetzt (5.1): „Werkzeug fehlt“ → Bau-Aufgabe
  (`task_spec_for_missing_capability`, über den Chat: „jarvis baue mir …“).
- Umgesetzt (5.2): Tool-Code laden über `load_plugin_tools` — **nur** wenn
  `JARVIS_ALLOW_PLUGIN_CODE=1` (Default aus; Code wird sonst nicht importiert).
- Offen: Plugin-Tools automatisch in die Tool-Registry einhängen und im
  Freigabe-Kern als Vorschlag führen.
