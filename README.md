# Jarvis Appliance OS (offline-first)

Dieses Repo baut ein bootbares Jarvis-Image (USB/SSD), das automatisch startet:
- `jarvis-backend.service` (FastAPI auf `127.0.0.1:8000`)
- `jarvis-kiosk.service` (Chromium Kiosk auf `http://127.0.0.1:8000/static/static-v4-tts.html`)

## Quick deploy auf laufender Ubuntu-VM
```bash
sudo ./scripts/deploy_local.sh
```

Das Deployment ist idempotent und installiert/aktualisiert:
- `/opt/jarvis` (Sync via `rsync -a --delete`)
- Python venv in `/opt/jarvis/.venv`
- systemd units (`jarvis-backend`, `jarvis-kiosk`, `jarvis` legacy)
- Modellordner:
  - `/opt/jarvis/models/llm`
  - `/opt/jarvis/models/stt`
  - `/opt/jarvis/models/tts`

## Bootbares Image bauen (`image.raw`)
```bash
./scripts/build-image.sh
```

Das Build-Script erstellt eine Stage und installiert Python-Dependencies **vorab** in die venv,
sodass beim Boot **kein pip/apt nötig** ist.

## USB flashen
> Achtung: Zielgerät wird überschrieben.

```bash
sudo dd if=build-output/image.raw of=/dev/sdX bs=4M status=progress oflag=sync
```

## First boot Verhalten
- `first-boot-wizard.service` läuft einmal.
- Marker: `/var/lib/jarvis/firstboot.done`
- Ruft `deploy_local.sh` mit `SKIP_PIP_INSTALL=1` auf (keine Runtime-Downloads am Boot).
- Danach laufen Backend + Kiosk automatisch.

## Offline Modelle (keine Binärmodelle im Git)
Modelle werden **nicht** ins Repo committed.

Pfade:
- `/opt/jarvis/models/llm`
- `/opt/jarvis/models/stt`
- `/opt/jarvis/models/tts`

Status prüfen:
```bash
/opt/jarvis/scripts/check_models.sh
```

Wenn Modelle fehlen, zeigt die UI ein Warning-Banner und bleibt trotzdem nutzbar.
Nach dem Kopieren von Modellen:
```bash
sudo systemctl restart jarvis-backend.service
```

## Logs
```bash
journalctl -u jarvis-backend -f
journalctl -u jarvis-kiosk -f
```

## Troubleshooting
- `status=203/EXEC`: Prüfe `/opt/jarvis/.venv/bin/uvicorn` und redeploy:
  ```bash
  sudo ./scripts/deploy_local.sh
  ```
- Kiosk startet nicht: prüfe Chromium/Xorg in Journal:
  ```bash
  journalctl -u jarvis-kiosk -n 200 --no-pager
  ```
