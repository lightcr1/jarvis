#!/usr/bin/env bash
set -euo pipefail

ensure_node_npm() {
  if command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1; then
    return 0
  fi

  if [[ "${EUID}" -ne 0 ]]; then
    echo "ERROR: Node.js/npm missing. Run as root to auto-install, or install manually." >&2
    return 1
  fi

  if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y nodejs npm
    return 0
  fi

  echo "ERROR: Unsupported package manager. Install Node.js + npm manually." >&2
  return 1
}

if command -v sst >/dev/null 2>&1; then
  echo "SST already installed: $(sst --version)"
  exit 0
fi

ensure_node_npm

if ! command -v npm >/dev/null 2>&1; then
  echo "ERROR: npm still unavailable after install attempt." >&2
  exit 1
fi

npm install -g sst

echo "Node: $(node --version)"
echo "npm: $(npm --version)"
echo "SST installed: $(sst --version)"
