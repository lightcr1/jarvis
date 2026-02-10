#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_DIR="${ROOT_DIR}/build-output"
STAGE_DIR="${ROOT_DIR}/.mkosi-stage"

if ! command -v mkosi >/dev/null 2>&1; then
  echo "mkosi not installed. Install mkosi or build inside a container that provides it."
  exit 1
fi

rm -rf "${STAGE_DIR}"
mkdir -p "${STAGE_DIR}" "${OUTPUT_DIR}"

rsync -a --delete \
  --exclude '.git/' \
  --exclude '.venv/' \
  --exclude 'build-output/' \
  "${ROOT_DIR}/" "${STAGE_DIR}/"

python3 -m venv "${STAGE_DIR}/.venv"
"${STAGE_DIR}/.venv/bin/python" -m pip install --upgrade pip
"${STAGE_DIR}/.venv/bin/python" -m pip install -r "${STAGE_DIR}/requirements.txt"
"${STAGE_DIR}/.venv/bin/python" -m pip install "uvicorn[standard]"

mkosi --directory "${STAGE_DIR}" --output-dir "${OUTPUT_DIR}" --force

echo "Image built in ${OUTPUT_DIR}"
echo "Expected raw disk artifact: ${OUTPUT_DIR}/image.raw"
