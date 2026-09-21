#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPLOY_DIR="$ROOT/deploy/openhands"
ENV_FILE="$DEPLOY_DIR/.env"
RUNPOD_ENV="${1:-/home/media/runpod/.env}"
INSTALL_ROOT="${OPENHANDS_INSTALL_ROOT:-/opt/jarvis-openhands}"

for command_name in docker git openssl; do
  command -v "$command_name" >/dev/null || { echo "Missing command: $command_name" >&2; exit 1; }
done
[ -r "$RUNPOD_ENV" ] || { echo "Runpod env not readable: $RUNPOD_ENV" >&2; exit 1; }

model_token="$(sed -n 's/^MODEL_ACCESS_TOKEN=//p' "$RUNPOD_ENV" | tail -n 1)"
[ -n "$model_token" ] || { echo "MODEL_ACCESS_TOKEN is missing in $RUNPOD_ENV" >&2; exit 1; }
control_token="$(sed -n 's/^CONTROL_TOKEN=//p' "$RUNPOD_ENV" | tail -n 1)"
[ "$model_token" != "$control_token" ] || { echo "MODEL_ACCESS_TOKEN must differ from CONTROL_TOKEN" >&2; exit 1; }

docker network inspect runpod_default >/dev/null 2>&1 || {
  echo "Docker network runpod_default is missing. Start the runpod compose stack first." >&2
  exit 1
}

sudo install -d -m 0700 -o "$(id -u)" -g "$(id -g)" "$INSTALL_ROOT/state" "$INSTALL_ROOT/projects"
if [ ! -d "$INSTALL_ROOT/projects/jarvis/.git" ]; then
  git clone "$(git -C "$ROOT" remote get-url origin)" "$INSTALL_ROOT/projects/jarvis"
fi

cp "$DEPLOY_DIR/.env.example" "$ENV_FILE"
sed -i "s|^OPENHANDS_STATE_DIR=.*|OPENHANDS_STATE_DIR=$INSTALL_ROOT/state|" "$ENV_FILE"
sed -i "s|^OPENHANDS_PROJECTS_DIR=.*|OPENHANDS_PROJECTS_DIR=$INSTALL_ROOT/projects|" "$ENV_FILE"
chmod 0600 "$ENV_FILE"

docker compose --env-file "$ENV_FILE" -f "$DEPLOY_DIR/compose.yml" config --quiet
printf '%s\n' \
  "OpenHands is prepared." \
  "Start: docker compose --env-file $ENV_FILE -f $DEPLOY_DIR/compose.yml up -d" \
  "UI: http://127.0.0.1:8000/canvas" \
  "LLM model: openai/code" \
  "LLM base URL (inside Docker): http://controller:8080/code/v1" \
  "LLM API key: use MODEL_ACCESS_TOKEN from $RUNPOD_ENV"
