#!/usr/bin/env bash
set -euo pipefail

BASE="/opt/jarvis/models"
for kind in llm stt tts; do
  dir="${BASE}/${kind}"
  if [[ -d "${dir}" ]] && find "${dir}" -mindepth 1 -print -quit | grep -q .; then
    echo "[OK] ${kind}: models found in ${dir}"
  else
    echo "[MISSING] ${kind}: no model files in ${dir}"
  fi
done

echo "To install offline models: copy files into /opt/jarvis/models/<llm|stt|tts> then restart jarvis-backend.service"
exit 0
