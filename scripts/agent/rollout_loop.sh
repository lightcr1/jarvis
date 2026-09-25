#!/usr/bin/env bash
# Host-side timer entry for an owner-approved autonomy-loop rollout (7.5).
#
# The Admin UI only writes a request marker (it never executes anything on the
# host). This script runs on the host (cron/timer): if a rollout was requested
# and the installed loop differs from the versioned source, it calls
# install_loop.sh, which creates a backup and installs the tested copy.
#
# Usage:
#   scripts/agent/rollout_loop.sh            # nur bei Anforderung + Drift
#   scripts/agent/rollout_loop.sh --force    # immer installieren
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MARKER="${LOOP_ROLLOUT_MARKER:-/home/media/jarvis-openhands/autonomy/rollout-requested}"
FORCE=0

for arg in "$@"; do
  case "$arg" in
    --force) FORCE=1 ;;
    *) echo "Unknown argument: $arg (only --force is supported)" >&2; exit 2 ;;
  esac
done

if [ "$FORCE" -ne 1 ] && [ ! -f "$MARKER" ]; then
  echo "Kein Rollout angefordert ($MARKER fehlt) - nichts zu tun."
  exit 0
fi

if [ "$FORCE" -ne 1 ]; then
  if "$ROOT/scripts/agent/install_loop.sh" --check >/dev/null 2>&1; then
    echo "Kein Drift - installierte Kopie ist aktuell; Rollout entfaellt."
    rm -f "$MARKER"
    exit 0
  fi
fi

JARVIS_REPO="${JARVIS_REPO:-$ROOT}" "$ROOT/scripts/agent/install_loop.sh"
rm -f "$MARKER"
echo "Rollout abgeschlossen. Backup/Rollback siehe install_loop.sh-Ausgabe."
