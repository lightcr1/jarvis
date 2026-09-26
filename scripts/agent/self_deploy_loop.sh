#!/usr/bin/env bash
# Host-seitiger Timer-Einstieg fuer einen Self-Deploy (Plan 5.3).
#
# Besitzer/Admin schreiben nur einen Anforderungs-Marker (sie fuehren nichts auf
# dem Host aus). Dieses Skript laeuft auf dem Host (Cron) und fuehrt den
# containerisierten Deploy mit Health-Check und automatischem Rollback aus
# (Logik in jarvis.self_deploy, ueber scripts/agent/self_deploy_cli.py).
#
# Konfiguration (Env oder Datei):
#   SELF_DEPLOY_MARKER  Default: /home/media/jarvis-openhands/autonomy/self-deploy-requested
#   SELF_DEPLOY_ENV     Default: /home/media/jarvis-openhands/autonomy/self-deploy.env
#   SELF_DEPLOY_WORKDIR Default: Repo-Root (dort liegen die Compose-Dateien)
#
# Usage:
#   scripts/agent/self_deploy_loop.sh            # nur bei Anforderung
#   scripts/agent/self_deploy_loop.sh --force    # sofort deployen
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MARKER="${SELF_DEPLOY_MARKER:-/home/media/jarvis-openhands/autonomy/self-deploy-requested}"
ENV_FILE="${SELF_DEPLOY_ENV:-/home/media/jarvis-openhands/autonomy/self-deploy.env}"
FORCE=0

for arg in "$@"; do
  case "$arg" in
    --force) FORCE=1 ;;
    *) echo "Unknown argument: $arg (only --force is supported)" >&2; exit 2 ;;
  esac
done

if [ "$FORCE" -ne 1 ] && [ ! -f "$MARKER" ]; then
  echo "Kein Self-Deploy angefordert ($MARKER fehlt) - nichts zu tun."
  exit 0
fi

# Konfiguration laden (Variablen exportieren, damit die Skripte sie sehen).
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

WORKDIR="${SELF_DEPLOY_WORKDIR:-$ROOT}"
cd "$WORKDIR"

if /usr/bin/python3 "$ROOT/scripts/agent/self_deploy_cli.py"; then
  rm -f "$MARKER"
  echo "Self-Deploy abgeschlossen."
else
  rc=$?
  rm -f "$MARKER"
  echo "Self-Deploy fehlgeschlagen (rc=$rc) - Rollback wurde ausgefuehrt." >&2
  exit "$rc"
fi
