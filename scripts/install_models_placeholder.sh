#!/usr/bin/env bash
set -euo pipefail

echo "This placeholder does not download large model binaries automatically."
echo "If internet is available, you can add your own download commands here."
echo "Offline method: copy models to:"
echo "  /opt/jarvis/models/llm"
echo "  /opt/jarvis/models/stt"
echo "  /opt/jarvis/models/tts"
echo "Then run: sudo systemctl restart jarvis-backend.service"
