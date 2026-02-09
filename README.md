# jarvis
Jarvis ist ein Text- und Voice-Assistant mit Skill-Engine, Security-Policy und optionalem Cloud-KI-Fallback.

## Orb-UI (Voice)
Die Orb-Oberfläche (`/static/orb-v2.html`) nutzt bereits STT + TTS:
- Spracheingabe → `/stt`
- Antwort → `/chat` → Audioausgabe über `/tts`
Wenn `/tts` nicht erreichbar ist, nutzt die Orb-UI automatisch den Browser-Voice-Fallback (SpeechSynthesis).

Damit die Sprachausgabe funktioniert, muss TTS korrekt konfiguriert sein:
- `PIPER_BIN` (Pfad zum piper Binary)
- `PIPER_MODEL` (Pfad zum Voice-Model)

## Sudo für Status-/Service-Kommandos
System-Kommandos (z.B. `status jarvis`) werden serverseitig über `sudo` ausgeführt.
**Passwörter werden nicht im Code gespeichert oder übermittelt.**

Empfehlung: `NOPASSWD`-Regel in der Sudoers-Datei für die benötigten Befehle (z.B. `systemctl`, `docker`, `ping`),
statt ein Passwort im Frontend/Backend zu hinterlegen.

## Proxmox (Read-only)
Das Backend bietet eine einfache Read-only-Integration für Proxmox-Hosts.
Hosts werden per API-Token hinzugefügt und anschließend über Read-only-Endpoints abgefragt.

**Wichtig:** API-Tokens werden lokal in `proxmox_hosts.json` gespeichert (Dateirechte 0600).

Beispiel: Host hinzufügen (requires `Authorization: Bearer <token>` vom `/unlock`-Endpoint):
```bash
curl -X POST http://localhost:8000/proxmox/hosts \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JARVIS_TOKEN" \
  -d '{"name":"pve-1","base_url":"https://pve.local:8006","api_token":"USER@REALM!TOKEN=SECRET","verify_tls":true}'
```

Beispiel: Nodes abrufen:
```bash
curl http://localhost:8000/proxmox/hosts/<host_id>/nodes
```

Beispiel: VM/LXC Status (Chat-Skill):
- `pve vm status <host_id> <node> <vmid>`
- `pve lxc status <host_id> <node> <vmid>`

Beispiel: VM/LXC Status (API):
```bash
curl http://localhost:8000/proxmox/hosts/<host_id>/nodes/<node>/vms/<vmid>/status
curl http://localhost:8000/proxmox/hosts/<host_id>/nodes/<node>/containers/<vmid>/status
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
