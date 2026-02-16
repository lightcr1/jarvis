#!/usr/bin/env bash
set -euo pipefail

if command -v sst >/dev/null 2>&1; then
  echo "SST already installed: $(sst --version)"
  exit 0
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "ERROR: npm not found. Install Node.js + npm first, then rerun this script." >&2
  exit 1
fi

npm install -g sst

echo "SST installed: $(sst --version)"
