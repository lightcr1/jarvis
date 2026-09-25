#!/usr/bin/env bash
# Compact recursive grep for agent rounds.
#
# Usage:
#   scripts/agent/find.sh <begriff> [pfad]
#
# Excludes node_modules, dist, build, .git, __pycache__, venvs and caps the
# number of hits (default 80, override with LIMIT=).
set -euo pipefail

TERM="${1:-}"
TARGET="${2:-.}"
LIMIT="${LIMIT:-80}"
if [ -z "$TERM" ]; then
  echo "Usage: scripts/agent/find.sh <begriff> [pfad]" >&2
  exit 2
fi

grep -rnI \
  --exclude-dir=node_modules \
  --exclude-dir=dist \
  --exclude-dir=build \
  --exclude-dir=.git \
  --exclude-dir=__pycache__ \
  --exclude-dir=.venv \
  --exclude-dir=venv \
  -m 5 \
  -- "$TERM" "$TARGET" 2>/dev/null | head -n "$LIMIT"
