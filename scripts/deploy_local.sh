#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="${SOURCE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
INSTALL_DIR="/opt/jarvis"
VENV_DIR="${INSTALL_DIR}/.venv"
VENV_PYTHON="${VENV_DIR}/bin/python"
CONFIG_DIR="/etc/jarvis"
CONFIG_FILE="${CONFIG_DIR}/config.env"
SERVICE_SRC="${INSTALL_DIR}/systemd/jarvis.service"
SERVICE_DST="/etc/systemd/system/jarvis.service"
RUN_SCRIPT="${INSTALL_DIR}/scripts/run_jarvis.sh"
HEALTH_URL_HTTP="http://localhost:8000/health"
HEALTH_URL_HTTPS="https://localhost:8000/health"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

if [[ "${EUID}" -ne 0 ]]; then
  fail "Run as root (use sudo)."
fi

command -v rsync >/dev/null 2>&1 || fail "rsync is required. Install it and retry."
command -v python3 >/dev/null 2>&1 || fail "python3 is required. Install it and retry."
command -v systemctl >/dev/null 2>&1 || fail "systemctl is required on this host."
command -v openssl >/dev/null 2>&1 || fail "openssl is required for TLS certificate generation."

INSTALL_SST="${INSTALL_SST:-0}"

mkdir -p "${INSTALL_DIR}"
if [[ "$(realpath "${SOURCE_DIR}")" != "$(realpath "${INSTALL_DIR}")" ]]; then
  rsync -a --delete "${SOURCE_DIR}/" "${INSTALL_DIR}/" || fail "Failed to sync repo to ${INSTALL_DIR}."
else
  echo "Source already at ${INSTALL_DIR}; skipping rsync sync step."
fi

if [[ ! -d "${VENV_DIR}" ]]; then
  python3 -m venv "${VENV_DIR}" || fail "Failed to create venv at ${VENV_DIR}."
fi

[[ -x "${VENV_PYTHON}" ]] || fail "Python executable missing in venv: ${VENV_PYTHON}"

"${VENV_PYTHON}" -m pip install --upgrade pip || fail "Failed to upgrade pip in venv."
"${VENV_PYTHON}" -m pip install -r "${INSTALL_DIR}/requirements.txt" || fail "Failed to install requirements.txt"
"${VENV_PYTHON}" -m pip install "uvicorn[standard]" || fail "Failed to install uvicorn[standard]"

if [[ ! -x "${VENV_DIR}/bin/uvicorn" ]]; then
  fail "uvicorn executable missing at ${VENV_DIR}/bin/uvicorn after install."
fi

[[ -f "${RUN_SCRIPT}" ]] || fail "Missing runtime launcher: ${RUN_SCRIPT}"
chmod 755 "${RUN_SCRIPT}" || fail "Failed to make ${RUN_SCRIPT} executable"

if [[ "${INSTALL_SST}" == "1" ]]; then
  if [[ -x "${INSTALL_DIR}/scripts/install_sst.sh" ]]; then
    "${INSTALL_DIR}/scripts/install_sst.sh" || fail "INSTALL_SST=1 but SST installation failed."
  else
    fail "INSTALL_SST=1 but missing ${INSTALL_DIR}/scripts/install_sst.sh"
  fi
fi

mkdir -p "${CONFIG_DIR}"
if [[ ! -f "${CONFIG_FILE}" ]]; then
  cp "${INSTALL_DIR}/config/jarvis.env.example" "${CONFIG_FILE}" || fail "Failed to create ${CONFIG_FILE}"
fi
chmod 600 "${CONFIG_FILE}" || fail "Failed to chmod 600 ${CONFIG_FILE}"

# Load runtime configuration from EnvironmentFile for TLS-aware deploy checks
set -a
# shellcheck disable=SC1090
source "${CONFIG_FILE}"
set +a

# Ensure admin data store env defaults exist so runtime + ops scripts are aligned.
ensure_env_default() {
  local key="$1"
  local value="$2"
  if ! grep -q "^${key}=" "${CONFIG_FILE}"; then
    echo "${key}=${value}" >> "${CONFIG_FILE}"
  fi
}

ensure_env_default "JARVIS_AUDIT_LOG_PATH" "/var/lib/jarvis/audit.log"
ensure_env_default "JARVIS_USER_STORE_PATH" "/var/lib/jarvis/users.json"
ensure_env_default "JARVIS_GROUP_STORE_PATH" "/var/lib/jarvis/groups.json"
ensure_env_default "JARVIS_MEMBERSHIP_STORE_PATH" "/var/lib/jarvis/memberships.json"
ensure_env_default "JARVIS_PERMISSION_STORE_PATH" "/var/lib/jarvis/permissions.json"
ensure_env_default "JARVIS_ADMIN_SETTINGS_PATH" "/var/lib/jarvis/admin_settings.json"
ensure_env_default "JARVIS_INTEGRITY_FAIL_ON_ORPHANS" "0"
ensure_env_default "JARVIS_INTEGRITY_FAIL_ON_ADMIN_LOCKOUT" "0"
ensure_env_default "JARVIS_INTEGRITY_FAIL_ON_DUPLICATE_MEMBERSHIPS" "0"

# Reload after defaults so variables are available below.
set -a
# shellcheck disable=SC1090
source "${CONFIG_FILE}"
set +a

ADMIN_DATA_PATHS=(
  "${JARVIS_AUDIT_LOG_PATH}"
  "${JARVIS_USER_STORE_PATH}"
  "${JARVIS_GROUP_STORE_PATH}"
  "${JARVIS_MEMBERSHIP_STORE_PATH}"
  "${JARVIS_PERMISSION_STORE_PATH}"
  "${JARVIS_ADMIN_SETTINGS_PATH}"
)

seed_admin_data_file() {
  local path="$1"
  local base
  base="$(basename "${path}")"
  case "${base}" in
    users.json)
      printf '%s\n' '{"users": {}}' > "${path}"
      ;;
    groups.json)
      printf '%s\n' '{"groups": {}}' > "${path}"
      ;;
    memberships.json)
      printf '%s\n' '{"memberships": []}' > "${path}"
      ;;
    permissions.json)
      printf '%s\n' '{"group_permissions": {}, "user_permissions": {}}' > "${path}"
      ;;
    admin_settings.json)
      printf '%s\n' '{"usage_limits": {"token_ttl_min": 20, "max_active_tokens": 200}, "voice": {"wakeword_enabled": false, "wakeword_phrase": "hey jarvis", "stt_provider": "local"}}' > "${path}"
      ;;
    audit.log)
      : > "${path}"
      ;;
    *)
      : > "${path}"
      ;;
  esac
}

for p in "${ADMIN_DATA_PATHS[@]}"; do
  [[ -n "${p}" ]] || continue
  mkdir -p "$(dirname "${p}")"
  if [[ ! -f "${p}" ]]; then
    seed_admin_data_file "${p}"
  fi
done

chmod 640 "${JARVIS_AUDIT_LOG_PATH}" "${JARVIS_USER_STORE_PATH}" "${JARVIS_GROUP_STORE_PATH}" "${JARVIS_MEMBERSHIP_STORE_PATH}" "${JARVIS_PERMISSION_STORE_PATH}" "${JARVIS_ADMIN_SETTINGS_PATH}" || fail "Failed to set permissions on admin data files"

TLS_CERT="${JARVIS_TLS_CERT_FILE:-}"
TLS_KEY="${JARVIS_TLS_KEY_FILE:-}"
TLS_ACTIVE="0"

# Default TLS paths if unset: ensure deploy brings HTTPS up immediately
if [[ -z "${TLS_CERT}" && -z "${TLS_KEY}" ]]; then
  TLS_CERT="/etc/jarvis/tls/fullchain.pem"
  TLS_KEY="/etc/jarvis/tls/privkey.pem"
  if ! grep -q '^JARVIS_TLS_CERT_FILE=' "${CONFIG_FILE}"; then
    echo "JARVIS_TLS_CERT_FILE=${TLS_CERT}" >> "${CONFIG_FILE}"
  fi
  if ! grep -q '^JARVIS_TLS_KEY_FILE=' "${CONFIG_FILE}"; then
    echo "JARVIS_TLS_KEY_FILE=${TLS_KEY}" >> "${CONFIG_FILE}"
  fi
fi

if [[ -n "${TLS_CERT}" || -n "${TLS_KEY}" ]]; then
  [[ -n "${TLS_CERT}" && -n "${TLS_KEY}" ]] || fail "Set both JARVIS_TLS_CERT_FILE and JARVIS_TLS_KEY_FILE (or neither)."

  TLS_DIR="/etc/jarvis/tls"
  mkdir -p "${TLS_DIR}"

  # Idempotent self-signed generation when configured files are missing
  if [[ ! -f "${TLS_CERT}" || ! -f "${TLS_KEY}" ]]; then
    echo "TLS enabled in config; generating self-signed certificate (idempotent)."
    openssl req -x509 -nodes -newkey rsa:2048 \
      -keyout "${TLS_KEY}" \
      -out "${TLS_CERT}" \
      -days 825 \
      -subj "/CN=$(hostname -f 2>/dev/null || hostname)" \
      >/dev/null 2>&1 || fail "Failed to generate self-signed TLS certificate/key."
  fi

  chmod 600 "${TLS_KEY}" || fail "Failed to chmod 600 ${TLS_KEY}"
  chmod 644 "${TLS_CERT}" || fail "Failed to chmod 644 ${TLS_CERT}"
  TLS_ACTIVE="1"
fi

[[ -f "${SERVICE_SRC}" ]] || fail "Missing service template: ${SERVICE_SRC}"
install -m 0644 "${SERVICE_SRC}" "${SERVICE_DST}" || fail "Failed to install systemd service."

systemctl daemon-reload || fail "systemctl daemon-reload failed"
systemctl enable --now jarvis.service || fail "Failed to enable/start jarvis.service"

systemctl --no-pager --full status jarvis.service || true

if [[ "${TLS_ACTIVE}" == "1" ]]; then
  echo "Health URL: ${HEALTH_URL_HTTPS}"
  curl -kfsS "${HEALTH_URL_HTTPS}" || fail "HTTPS health check failed"
else
  echo "Health URL: ${HEALTH_URL_HTTP}"
  curl -fsS "${HEALTH_URL_HTTP}" || fail "HTTP health check failed"
fi

if [[ -x "${INSTALL_DIR}/scripts/check_admin_data_integrity.sh" ]]; then
  "${INSTALL_DIR}/scripts/check_admin_data_integrity.sh" || fail "Admin data integrity check failed"
fi
