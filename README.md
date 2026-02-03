# jarvis
Jarvis ist ein Text- und Voice-Assistant mit KI-Funktionen.

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
