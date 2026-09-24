#!/usr/bin/env bash
# Installiert die Werkzeuge, die der Agent-Container intern braucht (pytest usw.),
# offline aus auf der Host-VM vorbereiteten Wheels. Der Container selbst hat kein
# Internet (openhands_agent-isolated: internal), deshalb werden die Pakete hier
# geholt und per `docker cp` ins laufende/neu gestartete Image eingespielt.
#
# Nach einem Container-Recreate ausfuehren:
#   bash scripts/agent/install_container_tools.sh
set -euo pipefail

CONTAINER="${CONTAINER:-jarvis-openhands}"
WHEEL_DIR="${WHEEL_DIR:-/tmp/jarvis-container-wheels}"
HOST_PY="${HOST_PY:-/home/media/runpod/.venv/bin/python}"
PACKAGES="${PACKAGES:-pytest pytest-asyncio}"

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "Fehler: Container '$CONTAINER' laeuft nicht." >&2
  exit 1
fi

echo "==> Wheels auf der Host-VM vorbereiten ($WHEEL_DIR)"
rm -rf "$WHEEL_DIR"
mkdir -p "$WHEEL_DIR"
[ -x "$HOST_PY" ] || { echo "Host-Python fehlt: $HOST_PY" >&2; exit 1; }
"$HOST_PY" -m pip download $PACKAGES -q -d "$WHEEL_DIR"

echo "==> Wheels in Container '$CONTAINER' kopieren"
docker cp "$WHEEL_DIR" "$CONTAINER:/tmp/container_tools_wheels"

echo "==> Offline installieren (kein Netzwerk im Container noetig)"
docker exec "$CONTAINER" sh -lc \
  'pip install --no-index --find-links /tmp/container_tools_wheels pytest pytest-asyncio -q && \
   python3 -c "import pytest; print(\"pytest\", pytest.__version__)"'

echo "OK: Container-Werkzeuge sind installiert."
