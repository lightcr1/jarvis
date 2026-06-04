#!/usr/bin/env bash
# J.A.R.V.I.S. Installer
# Usage: sudo bash install.sh
# Unattended: JARVIS_ADMIN_PASSWORD=secret JARVIS_PORT=443 sudo -E bash install.sh
set -euo pipefail

# ── Colours ──────────────────────────────────────────────────────────────────
if [[ -t 1 ]]; then
  BOLD='\033[1m'; DIM='\033[2m'; RESET='\033[0m'
  GREEN='\033[0;32m'; YELLOW='\033[0;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'
else
  BOLD=''; DIM=''; RESET=''; GREEN=''; YELLOW=''; RED=''; CYAN=''
fi

STEP=0
TOTAL=7

step() { STEP=$((STEP+1)); echo -e "\n${BOLD}${CYAN}[ ${STEP}/${TOTAL} ]${RESET} ${BOLD}$*${RESET}"; }
ok()   { echo -e "  ${GREEN}✓${RESET}  $*"; }
info() { echo -e "  ${DIM}→${RESET}  $*"; }
warn() { echo -e "  ${YELLOW}!${RESET}  $*"; }
fail() { echo -e "\n${RED}${BOLD}ERROR:${RESET} $*" >&2; exit 1; }
ask()  { echo -en "  ${BOLD}$1${RESET} "; read -r "$2"; }
askp() { echo -en "  ${BOLD}$1${RESET} "; read -rs "$2"; echo; }

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/jarvis"
CONFIG_DIR="/etc/jarvis"
CONFIG_FILE="${CONFIG_DIR}/config.env"

# ── Banner ────────────────────────────────────────────────────────────────────
echo -e ""
echo -e "${BOLD}${CYAN}  ┌─────────────────────────────────────────┐${RESET}"
echo -e "${BOLD}${CYAN}  │   J . A . R . V . I . S .  Installer   │${RESET}"
echo -e "${BOLD}${CYAN}  │   Just A Rather Very Intelligent System  │${RESET}"
echo -e "${BOLD}${CYAN}  └─────────────────────────────────────────┘${RESET}"
echo -e ""

# ── Root check ────────────────────────────────────────────────────────────────
[[ "${EUID}" -eq 0 ]] || fail "Run as root: sudo bash $0"

# ── OS detection ─────────────────────────────────────────────────────────────
step "Checking system"
if [[ -f /etc/os-release ]]; then
  . /etc/os-release
  info "Detected: ${PRETTY_NAME:-Linux}"
else
  warn "Cannot detect OS — assuming Debian/Ubuntu compatible."
fi

APT_AVAILABLE=0
command -v apt-get >/dev/null 2>&1 && APT_AVAILABLE=1

# ── Install system dependencies ──────────────────────────────────────────────
step "Installing system dependencies"
MISSING=()
for cmd in python3 rsync openssl curl; do
  command -v "$cmd" >/dev/null 2>&1 || MISSING+=("$cmd")
done
command -v node >/dev/null 2>&1 || MISSING+=("nodejs")
command -v npm  >/dev/null 2>&1 || MISSING+=("npm")

if [[ ${#MISSING[@]} -gt 0 ]]; then
  if [[ "${APT_AVAILABLE}" -eq 1 ]]; then
    info "Installing: ${MISSING[*]}"
    apt-get update -qq
    apt-get install -y python3 python3-venv python3-pip rsync openssl curl nodejs npm 2>&1 \
      | grep -E '^(Get|Setting|Unpacking|Processing)' | sed 's/^/    /' || true
    ok "System packages installed"
  else
    fail "Missing: ${MISSING[*]}. Install them manually and re-run."
  fi
else
  ok "All dependencies present"
fi

# Verify python3-venv is available
python3 -m venv --help >/dev/null 2>&1 || {
  [[ "${APT_AVAILABLE}" -eq 1 ]] && apt-get install -y python3-venv -qq
}

# ── Configuration wizard ──────────────────────────────────────────────────────
step "Configuration"

# Port
JARVIS_PORT="${JARVIS_PORT:-}"
if [[ -z "${JARVIS_PORT}" ]]; then
  ask "Port to listen on [443]:" _port
  JARVIS_PORT="${_port:-443}"
fi
ok "Port: ${JARVIS_PORT}"

# Admin password
JARVIS_ADMIN_PASSWORD="${JARVIS_ADMIN_PASSWORD:-}"
if [[ -z "${JARVIS_ADMIN_PASSWORD}" ]]; then
  while true; do
    askp "Admin password (min 8 chars):" _pw1
    [[ ${#_pw1} -ge 8 ]] && break
    warn "Password must be at least 8 characters."
  done
  askp "Confirm admin password:" _pw2
  [[ "${_pw1}" == "${_pw2}" ]] || fail "Passwords do not match."
  JARVIS_ADMIN_PASSWORD="${_pw1}"
fi
ok "Admin password set"

# Gemini API key (optional)
JARVIS_GEMINI_API_KEY="${JARVIS_GEMINI_API_KEY:-}"
if [[ -z "${JARVIS_GEMINI_API_KEY}" ]]; then
  ask "Gemini API key (optional, press Enter to skip):" _gemini
  JARVIS_GEMINI_API_KEY="${_gemini:-}"
fi
if [[ -n "${JARVIS_GEMINI_API_KEY}" ]]; then
  ok "Gemini API key set"
else
  info "Skipping Gemini — JARVIS will use local LLM fallback"
fi

# Home Assistant (optional)
JARVIS_HA_BASE_URL="${JARVIS_HA_BASE_URL:-}"
JARVIS_HA_TOKEN="${JARVIS_HA_TOKEN:-}"
if [[ -z "${JARVIS_HA_BASE_URL}" ]]; then
  ask "Home Assistant URL (optional, e.g. http://homeassistant.local:8123):" _ha_url
  JARVIS_HA_BASE_URL="${_ha_url:-}"
fi
if [[ -n "${JARVIS_HA_BASE_URL}" && -z "${JARVIS_HA_TOKEN}" ]]; then
  askp "Home Assistant long-lived token:" _ha_token
  JARVIS_HA_TOKEN="${_ha_token:-}"
fi
[[ -n "${JARVIS_HA_BASE_URL}" ]] && ok "Home Assistant: ${JARVIS_HA_BASE_URL}" || info "Skipping Home Assistant"

# Tailscale
JARVIS_TAILSCALE="${JARVIS_TAILSCALE:-}"
if [[ -z "${JARVIS_TAILSCALE}" ]]; then
  ask "Set up Tailscale for remote access + HTTPS? [Y/n]:" _ts
  _ts="${_ts:-Y}"
  [[ "${_ts}" =~ ^[Yy] ]] && JARVIS_TAILSCALE="yes" || JARVIS_TAILSCALE="no"
fi
[[ "${JARVIS_TAILSCALE}" == "yes" ]] && ok "Tailscale: will set up after deploy" || info "Skipping Tailscale"

# ── Pre-populate config ───────────────────────────────────────────────────────
step "Writing configuration"

mkdir -p "${CONFIG_DIR}"
if [[ ! -f "${CONFIG_FILE}" ]]; then
  if [[ -f "${INSTALL_DIR}/config/jarvis.env.example" ]]; then
    cp "${INSTALL_DIR}/config/jarvis.env.example" "${CONFIG_FILE}"
  elif [[ -f "${REPO_DIR}/config/jarvis.env.example" ]]; then
    cp "${REPO_DIR}/config/jarvis.env.example" "${CONFIG_FILE}"
  else
    : > "${CONFIG_FILE}"
  fi
fi

set_config() {
  local key="$1" val="$2"
  if grep -q "^${key}=" "${CONFIG_FILE}" 2>/dev/null; then
    sed -i "s|^${key}=.*|${key}=${val}|" "${CONFIG_FILE}"
  else
    echo "${key}=${val}" >> "${CONFIG_FILE}"
  fi
}

set_config "JARVIS_PORT"            "${JARVIS_PORT}"
set_config "JARVIS_ADMIN_PASSWORD"  "${JARVIS_ADMIN_PASSWORD}"
[[ -n "${JARVIS_GEMINI_API_KEY}" ]] && set_config "JARVIS_GEMINI_API_KEY" "${JARVIS_GEMINI_API_KEY}"
[[ -n "${JARVIS_HA_BASE_URL}"    ]] && set_config "JARVIS_HA_BASE_URL"    "${JARVIS_HA_BASE_URL}"
[[ -n "${JARVIS_HA_TOKEN}"       ]] && set_config "JARVIS_HA_TOKEN"       "${JARVIS_HA_TOKEN}"
chmod 600 "${CONFIG_FILE}"

ok "Config written to ${CONFIG_FILE}"

# ── Run deploy ────────────────────────────────────────────────────────────────
step "Installing JARVIS"
info "This builds the frontend and sets up the Python backend — takes ~2 minutes."
echo ""

export SOURCE_DIR="${REPO_DIR}"
bash "${REPO_DIR}/scripts/deploy_local.sh" 2>&1 | sed 's/^/    /'

# ── Tailscale ────────────────────────────────────────────────────────────────
if [[ "${JARVIS_TAILSCALE}" == "yes" ]]; then
  step "Setting up Tailscale"
  if [[ -x "${INSTALL_DIR}/scripts/setup_tailscale.sh" ]]; then
    bash "${INSTALL_DIR}/scripts/setup_tailscale.sh"
  else
    bash "${REPO_DIR}/scripts/setup_tailscale.sh"
  fi
fi

# ── Summary ───────────────────────────────────────────────────────────────────
step "Done"

TAILSCALE_IP="$(tailscale ip -4 2>/dev/null || echo '')"
LOCAL_IP="$(hostname -I 2>/dev/null | awk '{print $1}' || echo 'your-server-ip')"

echo ""
echo -e "${BOLD}${GREEN}  ┌─────────────────────────────────────────┐${RESET}"
echo -e "${BOLD}${GREEN}  │   J.A.R.V.I.S. is live.                │${RESET}"
echo -e "${BOLD}${GREEN}  └─────────────────────────────────────────┘${RESET}"
echo ""

if [[ -n "${TAILSCALE_IP}" ]]; then
  echo -e "  ${BOLD}Remote URL (Tailscale):${RESET}  https://${TAILSCALE_IP}/"
fi
echo -e "  ${BOLD}Local URL:${RESET}               https://${LOCAL_IP}:${JARVIS_PORT}/"
echo -e "  ${BOLD}Admin login:${RESET}             admin / (password you set)"
echo -e "  ${BOLD}Admin dashboard:${RESET}         /dashboard"
echo ""
echo -e "  ${DIM}Quick deploy after code changes:${RESET}"
echo -e "  ${DIM}  sudo bash ${INSTALL_DIR}/scripts/deploy.sh${RESET}"
echo ""
echo -e "  ${DIM}View logs:${RESET}"
echo -e "  ${DIM}  sudo journalctl -u jarvis -f${RESET}"
echo ""
