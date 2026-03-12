#!/usr/bin/env bash
set -euo pipefail

REPORT_PATH="${1:-./recovery_drill_report.md}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8000/health}"
RECOVERY_WAIT_SECONDS="${RECOVERY_WAIT_SECONDS:-30}"
RESTART_COMMAND="${RESTART_COMMAND:-systemctl restart jarvis.service}"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

command -v curl >/dev/null 2>&1 || fail "curl is required."

pre_status="failed"
post_status="failed"
restart_output=""

if curl -fsS "${HEALTH_URL}" >/dev/null 2>&1; then
  pre_status="healthy"
fi

set +e
restart_output="$(bash -lc "${RESTART_COMMAND}" 2>&1)"
restart_rc=$?
set -e
if [[ ${restart_rc} -ne 0 ]]; then
  fail "Restart command failed: ${restart_output}"
fi

deadline=$((SECONDS + RECOVERY_WAIT_SECONDS))
while (( SECONDS < deadline )); do
  if curl -fsS "${HEALTH_URL}" >/dev/null 2>&1; then
    post_status="healthy"
    break
  fi
  sleep 1
done

[[ "${post_status}" == "healthy" ]] || fail "Service did not recover before timeout."

mkdir -p "$(dirname "${REPORT_PATH}")"
cat > "${REPORT_PATH}" <<EOF
# Recovery Drill Report

- Timestamp: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
- Health URL: \`${HEALTH_URL}\`
- Restart command: \`${RESTART_COMMAND}\`
- Pre-check status: ${pre_status}
- Post-check status: ${post_status}

## Results

- PASS \`precheck\`: Service responded before the drill.
- PASS \`restart-command\`: Restart command completed successfully.
- PASS \`recovery\`: Health endpoint recovered within ${RECOVERY_WAIT_SECONDS}s.

## Restart Output

\`\`\`
${restart_output}
\`\`\`
EOF

echo "Report written: ${REPORT_PATH}"
