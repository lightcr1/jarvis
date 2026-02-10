# jarvis
Jarvis ist ein Text- und Voice-Assistant mit Skill-Engine, Security-Policy und optionalem Cloud-KI-Fallback.

## Quick Deploy (Ubuntu VM, idempotent)
Nach einem Repo-Clone reicht:
```bash
sudo ./scripts/deploy_local.sh
```

Das Script erledigt idempotent:
- Sync nach `/opt/jarvis` via `rsync -a --delete`
- venv unter `/opt/jarvis/.venv` (falls nicht vorhanden)
- `pip install -r requirements.txt` + `uvicorn[standard]`
- `/etc/jarvis/config.env` aus `config/jarvis.env.example` (falls nicht vorhanden, danach `chmod 600`)
- Installation/Aktualisierung von `jarvis.service`
- `systemctl daemon-reload && systemctl enable --now jarvis.service`
- Ausgabe von Service-Status + Health-URL

Danach:
```bash
systemctl status jarvis.service
curl http://localhost:8000/health
```

## HTML-UI öffnen
Nach dem Start erreichst du die UI unter:
- `http://localhost:8000/` (standardmäßig Orb-UI)
- `http://localhost:8000/static/orb-v2.html`
- `http://localhost:8000/static/static-v4-tts.html`

## Troubleshooting
- **CHDIR / WorkingDirectory Fehler**
  - Symptom in Journal: `Failed at step CHDIR`.
  - Ursache: falsches Arbeitsverzeichnis.
  - Fix: Service verwendet `WorkingDirectory=/opt/jarvis`; erneut deployen:
    ```bash
    sudo ./scripts/deploy_local.sh
    ```

- **`No module named uvicorn`**
  - Ursache: venv/dependencies fehlen oder falscher Python-Interpreter.
  - Fix: Deploy-Script installiert `uvicorn[standard]` in `/opt/jarvis/.venv` und startet den Service mit diesem Binary:
    ```bash
    /opt/jarvis/.venv/bin/uvicorn
    ```

- **`status=203/EXEC` bei `jarvis.service`**
  - Ursache: `ExecStart` zeigt auf einen nicht existierenden/nicht ausführbaren Pfad (typisch: fehlendes venv oder fehlendes `uvicorn`).
  - Fix:
    ```bash
    sudo ./scripts/deploy_local.sh
    ```
    Das Deploy-Script prüft explizit, dass `/opt/jarvis/.venv/bin/uvicorn` vorhanden und ausführbar ist.

- **Service läuft, Seiten laden nicht**
  - Logs prüfen:
    ```bash
    sudo journalctl -u jarvis.service -n 200 --no-pager
    ```
  - Lokal testen:
    ```bash
    curl -i http://localhost:8000/health
    curl -i http://localhost:8000/
    ```

## Orb-UI (Voice)
Die Orb-Oberfläche (`/static/orb-v2.html`) nutzt STT + TTS:
- Spracheingabe → `/stt`
- Antwort → `/chat` → Audioausgabe über `/tts`
Wenn `/tts` nicht erreichbar ist, nutzt die Orb-UI den Browser-Voice-Fallback (SpeechSynthesis).

Damit lokale Sprachausgabe funktioniert, müssen gesetzt sein:
- `PIPER_BIN` (Pfad zum piper Binary)
- `PIPER_MODEL` (Pfad zum Voice-Model)

## Konfiguration (ohne Secrets im Repo)
Verwende `/etc/jarvis/config.env` (Template: `config/jarvis.env.example`).
- `JARVIS_PASSPHRASE`
- `ALLOWED_TARGETS` (deny-by-default für write/critical)
- `COOLDOWN_RESTART_SECONDS`, `COOLDOWN_CRITICAL_SECONDS`
- Optional: `PROXMOX_BASE_URL`, `PROXMOX_API_TOKEN`
- Optional: `OPENAI_API_KEY`, `GEMINI_API_KEY`

## Security-Model (Kurzfassung)
- read: kein Token nötig.
- write: Token + Confirm (`YES`).
- critical: Token + Plan + Confirm (`YES, proceed`).
- Targets müssen in `ALLOWED_TARGETS` stehen (deny-by-default).
- Cooldowns verhindern Restart-Loops.

## Build: Bootbares ISO/Disk-Image
Reproduzierbarer Build via `mkosi`:
```bash
scripts/build-image.sh
```

Beim Boot sorgt `first-boot-wizard` automatisch für Grundkonfiguration und ruft anschließend `scripts/deploy_local.sh` auf. Dadurch werden Dependencies installiert und `jarvis.service` automatisch aktiviert/gestartet.

## Legacy Installer
`install_service.sh` bleibt als Wrapper erhalten und ruft intern `deploy_local.sh` auf:
```bash
sudo ./scripts/install_service.sh
```

## Tests
```bash
python -m unittest discover -s tests
```

## Lokales Starten (MVP)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export JARVIS_PASSPHRASE=change-me
export ALLOWED_TARGETS=local
uvicorn jarvisappv4:app --host 0.0.0.0 --port 8000
```

Beispiele:
```bash
curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" -d '{"text":"status jarvis"}'
curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" -d '{"text":"skills --verbose"}'
```

## Konfiguration (ohne Secrets im Repo)
Verwende ENV oder eine Datei wie `/etc/jarvis/config.env` (siehe `config/jarvis.env.example`).
- `JARVIS_PASSPHRASE`
- `ALLOWED_TARGETS` (deny-by-default für write/critical)
- `COOLDOWN_RESTART_SECONDS`, `COOLDOWN_CRITICAL_SECONDS`
- Optional: `PROXMOX_BASE_URL`, `PROXMOX_API_TOKEN`
- Optional: `OPENAI_API_KEY`, `GEMINI_API_KEY`

## Security-Model (Kurzfassung)
- read: kein Token nötig.
- write: Token + Confirm (`YES`).
- critical: Token + Plan + Confirm (`YES, proceed`).
- Targets müssen in `ALLOWED_TARGETS` stehen (deny-by-default).
- Cooldowns verhindern Restart-Loops.

## Build: Bootbares ISO/Disk-Image
Reproduzierbarer Build via `mkosi`:
```bash
scripts/build-image.sh
```
Output unter `build-output/`. Das Image startet nach Boot automatisch (`systemd/jarvis.service`).

## First-Boot Wizard
Beim ersten Boot schreibt `first-boot-wizard` eine minimale Konfiguration:
- `/etc/jarvis/config.env`
- Statusdatei: `/var/lib/jarvis/first-boot.done`

## Update-Strategie
Empfohlen: neues Image bauen und per A/B-Update ausrollen. Im MVP werden keine automatischen Updates erzwungen.

## Requirements-Trace
Siehe `trace.md` für R1–R25 Status.

## Tests
```bash
python -m unittest discover -s tests
```
