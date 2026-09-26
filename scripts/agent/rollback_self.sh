#!/usr/bin/env bash
# Rollback fuer den containerisierten Self-Deploy (Plan 5.3).
#
# Liest den vorher gemerkten Image-Stand (scripts/agent/self_deploy.sh) und
# stellt ihn wieder her: das alte Image wird auf den erwarteten Namen getaggt
# und der Dienst neu erstellt.
#
# Env:
#   SELF_DEPLOY_COMPOSE_FILES  Pflicht, space-getrennt
#   SELF_DEPLOY_SERVICE        ueberschreibt SERVICE aus dem State
#   SELF_DEPLOY_STATE_FILE     Default: /var/lib/jarvis/self_deploy_state
set -euo pipefail

STATE_FILE="${SELF_DEPLOY_STATE_FILE:-/var/lib/jarvis/self_deploy_state}"
FILES="${SELF_DEPLOY_COMPOSE_FILES:-}"
[[ -n "$FILES" ]] || { echo "SELF_DEPLOY_COMPOSE_FILES fehlt" >&2; exit 2; }
[[ -f "$STATE_FILE" ]] || { echo "kein State ($STATE_FILE) -- nichts zurueckzurollen" >&2; exit 2; }

# shellcheck disable=SC1090
source "$STATE_FILE"
SERVICE="${SELF_DEPLOY_SERVICE:-${SERVICE:-jarvis}}"

COMPOSE=(docker compose)
for f in $FILES; do COMPOSE+=(-f "$f"); done

if [[ -n "${PREV_ID:-}" && -n "${PREV_NAME:-}" ]]; then
  echo "rollback: tagge ${PREV_ID} -> ${PREV_NAME}"
  docker tag "$PREV_ID" "$PREV_NAME"
fi
"${COMPOSE[@]}" up -d --force-recreate --no-deps "$SERVICE"
echo "rollback: ${SERVICE} wiederhergestellt (${PREV_NAME:-unbekannt})"
