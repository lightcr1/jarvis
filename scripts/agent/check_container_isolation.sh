#!/usr/bin/env bash
# Verify that an OpenHands work container only hangs in the allowed internal
# network(s) (Phase 6). Read-only: inspects Docker, changes nothing.
#
# Usage:
#   scripts/agent/check_container_isolation.sh [container] [allowed_networks_csv]
#
# Defaults: container=jarvis-openhands, allowed=agent-isolated.
# Exit 0 = isolated, 1 = unexpected network, 2 = container not found/docker missing.
set -euo pipefail

CONTAINER="${1:-jarvis-openhands}"
ALLOWED="${2:-agent-isolated}"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker nicht verfuegbar - Check uebersprungen." >&2
  exit 2
fi
if ! docker inspect "$CONTAINER" >/dev/null 2>&1; then
  echo "Container '$CONTAINER' nicht gefunden." >&2
  exit 2
fi

docker inspect -f '{{json .NetworkSettings.Networks}}' "$CONTAINER" | \
ALLOWED="$ALLOWED" "${PYTHON:-python3}" -c '
import json, os, sys
networks = json.load(sys.stdin) if not sys.stdin.isatty() else {}
allowed = {item.strip() for item in os.environ["ALLOWED"].split(",") if item.strip()}


def matches(name, allowed):
    # Docker prefixet Netzwerke mit dem Compose-Projekt (z. B. openhands_agent-isolated).
    return any(name == entry or name.endswith("_" + entry) for entry in allowed)


names = sorted(networks.keys())
extra = [name for name in names if not matches(name, allowed)]
print(f"Netzwerke: {names} | erlaubt: {sorted(allowed)}")
if extra:
    print(f"VERLETZUNG: unerwartete Netzwerke: {extra}", file=sys.stderr)
    sys.exit(1)
'
