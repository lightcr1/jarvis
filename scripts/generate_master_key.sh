#!/usr/bin/env bash
# Print a new Fernet master key for JARVIS_SECRET_KEY.
# Paste the output into .env (or /etc/jarvis/config.env) as:
#   JARVIS_SECRET_KEY=<value>
#
# The key is a bootstrap secret and is intentionally NOT editable through the
# Jarvis API. Keep it backed up: losing it makes encrypted credentials and the
# TOTP secret unrecoverable.
set -euo pipefail

python3 - <<'PY'
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
PY
