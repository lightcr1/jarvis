#!/usr/bin/env bash
# Run only the tests affected by the given paths, with compact output.
#
# Usage:
#   scripts/agent/verify.sh [pfade…]
#
# Without paths, the changed paths of the working tree are used. Always runs
# scripts/agent/check_policy.py on the same paths. Frontend paths trigger
# ``vitest run`` when node_modules is available.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  for cand in python3 /home/media/runpod/.venv/bin/python /opt/jarvis/.venv/bin/python; do
    if command -v "$cand" >/dev/null 2>&1 && "$cand" -c "import pytest" >/dev/null 2>&1; then
      PY="$cand"
      break
    fi
  done
fi
if [ -z "$PY" ]; then
  echo "Kein Python mit pytest gefunden (PYTHON setzen)." >&2
  exit 1
fi

if [ "$#" -gt 0 ]; then
  PATHS=("$@")
else
  mapfile -t PATHS < <(git diff --name-only --diff-filter=ACMR HEAD)
fi

echo "==> Policy-Check"
"$PY" scripts/agent/check_policy.py "${PATHS[@]}" >/dev/null && echo "    policy ok"

mapfile -t TESTS < <("$PY" scripts/agent/verify_map.py "${PATHS[@]}")
if [ "${#TESTS[@]}" -gt 0 ]; then
  echo "==> pytest (${#TESTS[@]} Datei(en))"
  "$PY" -m pytest -q -x --no-header -p no:cacheprovider "${TESTS[@]}" 2>&1 | tail -60
else
  echo "==> pytest: keine betroffenen Testdateien gefunden"
fi

FRONTEND_CHANGED=0
for path in "${PATHS[@]}"; do
  case "$path" in
    frontend/*) FRONTEND_CHANGED=1 ;;
  esac
done
if [ "$FRONTEND_CHANGED" -eq 1 ]; then
  if [ -d frontend/node_modules ]; then
    echo "==> vitest"
    (cd frontend && npx --no-install vitest run 2>&1 | tail -40)
  else
    echo "==> vitest uebersprungen (frontend/node_modules fehlt)"
  fi
fi
