#!/usr/bin/env bash
# Containerisierter Self-Deploy-Schritt (Plan 5.3).
#
# Baut/zieht das neue Image und startet den Dienst neu. Health-Check und Rollback
# liegen beim Aufrufer (jarvis.self_deploy.SelfDeployer); dieses Skript merkt
# sich vorher das aktuelle Image, damit scripts/agent/rollback_self.sh es
# wiederherstellen kann.
#
# Env:
#   SELF_DEPLOY_COMPOSE_FILES  Pflicht, space-getrennt, z.B. "a.yml b.yml"
#   SELF_DEPLOY_SERVICE        Default: jarvis
#   SELF_DEPLOY_IMAGE          Image-Name/Tag (fuer Rollback), z.B. ghcr.io/...:latest
#   SELF_DEPLOY_BUILD=1        docker compose build <service>
#   SELF_DEPLOY_PULL=1         docker compose pull <service>
#   SELF_DEPLOY_STATE_FILE     Default: /var/lib/jarvis/self_deploy_state
#
# --dry-run: nur zeigen, nichts ausfuehren.
set -euo pipefail

DRY=0
for arg in "$@"; do [[ "$arg" == "--dry-run" ]] && DRY=1; done

SERVICE="${SELF_DEPLOY_SERVICE:-jarvis}"
IMAGE="${SELF_DEPLOY_IMAGE:-}"
STATE_FILE="${SELF_DEPLOY_STATE_FILE:-/var/lib/jarvis/self_deploy_state}"
FILES="${SELF_DEPLOY_COMPOSE_FILES:-}"
[[ -n "$FILES" ]] || { echo "SELF_DEPLOY_COMPOSE_FILES fehlt" >&2; exit 2; }

COMPOSE=(docker compose)
for f in $FILES; do COMPOSE+=(-f "$f"); done

run() { if [[ "$DRY" == "1" ]]; then echo "[dry-run] $*"; else "$@"; fi; }

# 1) Aktuelles Image des Dienstes merken (fuer Rollback).
PREV_ID=""; PREV_NAME="$IMAGE"
if [[ "$DRY" != "1" ]]; then
  CONTAINER="$("${COMPOSE[@]}" ps -q "$SERVICE" 2>/dev/null | head -1 || true)"
  if [[ -n "$CONTAINER" ]]; then
    PREV_ID="$(docker inspect -f '{{.Image}}' "$CONTAINER" 2>/dev/null || true)"
    PREV_NAME="$(docker inspect -f '{{.Config.Image}}' "$CONTAINER" 2>/dev/null || echo "$IMAGE")"
  fi
  mkdir -p "$(dirname "$STATE_FILE")"
  printf 'PREV_ID=%s\nPREV_NAME=%s\nSERVICE=%s\n' "$PREV_ID" "$PREV_NAME" "$SERVICE" > "$STATE_FILE"
fi

# 2) Neu bauen/ziehen.
[[ "${SELF_DEPLOY_BUILD:-0}" == "1" ]] && run "${COMPOSE[@]}" build "$SERVICE"
[[ "${SELF_DEPLOY_PULL:-0}" == "1" ]] && run "${COMPOSE[@]}" pull "$SERVICE"

# 3) Neu starten.
run "${COMPOSE[@]}" up -d --no-deps "$SERVICE"
echo "self_deploy: ${SERVICE} aktualisiert (vorher ${PREV_NAME:-unbekannt})"
