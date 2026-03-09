#!/usr/bin/env bash
set -euo pipefail

# Prints repository size in MB and warns if above the threshold.
THRESHOLD_MB="${1:-500}"

SIZE_MB=$(du -sm . | awk '{print $1}')

echo "Repository size: ${SIZE_MB} MB"
echo "Threshold: ${THRESHOLD_MB} MB"

if [ "${SIZE_MB}" -le "${THRESHOLD_MB}" ]; then
  echo "OK: repository is within threshold"
  exit 0
fi

echo "WARNING: repository exceeds threshold"
exit 1
