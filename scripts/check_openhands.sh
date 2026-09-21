#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPLOY_DIR="$ROOT/deploy/openhands"
ENV_FILE="$DEPLOY_DIR/.env"
[ -r "$ENV_FILE" ] || { echo "Run scripts/prepare_openhands.sh first." >&2; exit 1; }
docker compose --env-file "$ENV_FILE" -f "$DEPLOY_DIR/compose.yml" config --quiet
docker compose --env-file "$ENV_FILE" -f "$DEPLOY_DIR/compose.yml" ps
bind_ip="$(sed -n 's/^OPENHANDS_BIND_IP=//p' "$ENV_FILE")"
port="$(sed -n 's/^OPENHANDS_PORT=//p' "$ENV_FILE")"
curl --fail --silent --show-error --max-time 10 "http://${bind_ip:-127.0.0.1}:${port:-8000}/canvas" >/dev/null
echo "OpenHands Agent Canvas is reachable."
