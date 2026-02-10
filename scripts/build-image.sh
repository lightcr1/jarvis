#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_DIR="${ROOT_DIR}/build-output"

if ! command -v mkosi >/dev/null 2>&1; then
  echo "mkosi not installed. Install mkosi or build inside a container that provides it."
  exit 1
fi

mkdir -p "${OUTPUT_DIR}"
mkosi --workspace-dir "${ROOT_DIR}" --output-dir "${OUTPUT_DIR}" --force

echo "Image built in ${OUTPUT_DIR}"
