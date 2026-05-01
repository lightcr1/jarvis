#!/usr/bin/env bash
# Download and install a high-quality British male Piper voice model.
# This is the closest free offline voice to the original J.A.R.V.I.S.
#
# Usage:
#   sudo bash scripts/install_piper_voice.sh
#   Then add to /etc/jarvis/config.env:
#     TTS_PROVIDER=piper
#     PIPER_MODEL=/opt/jarvis/models/en_GB-alan-medium.onnx
#
# Models ranked by JARVIS-likeness (British male):
#   en_GB-alan-medium   — recommended: clear, measured, British
#   en_GB-alan-low      — faster, slightly lower quality
#   en_GB-cori-high     — alternative British voice
#
# Source: https://huggingface.co/rhasspy/piper-voices

set -euo pipefail

MODEL_DIR="${PIPER_MODEL_DIR:-/opt/jarvis/models}"
VOICE="${1:-en_GB-alan-medium}"
BASE_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main"

declare -A VOICE_PATHS=(
  ["en_GB-alan-medium"]="en/en_GB/alan/medium/en_GB-alan-medium.onnx"
  ["en_GB-alan-low"]="en/en_GB/alan/low/en_GB-alan-low.onnx"
  ["en_GB-cori-high"]="en/en_GB/cori/high/en_GB-cori-high.onnx"
  ["en_US-ryan-high"]="en/en_US/ryan/high/en_US-ryan-high.onnx"
)

[[ -v "VOICE_PATHS[${VOICE}]" ]] || {
  echo "Unknown voice '${VOICE}'. Choose from: ${!VOICE_PATHS[*]}"
  exit 1
}

ONNX_PATH="${VOICE_PATHS[${VOICE}]}"
JSON_PATH="${ONNX_PATH}.json"
ONNX_FILE="${MODEL_DIR}/${VOICE}.onnx"
JSON_FILE="${ONNX_FILE}.json"

mkdir -p "${MODEL_DIR}"

echo "Downloading ${VOICE} model..."
curl -L --progress-bar "${BASE_URL}/${ONNX_PATH}" -o "${ONNX_FILE}"
curl -L --progress-bar "${BASE_URL}/${JSON_PATH}" -o "${JSON_FILE}"

echo ""
echo "======================================================"
echo "Voice installed: ${ONNX_FILE}"
echo ""
echo "Add to /etc/jarvis/config.env:"
echo "  TTS_PROVIDER=piper"
echo "  PIPER_MODEL=${ONNX_FILE}"
echo "  PIPER_LENGTH_SCALE=1.10   # slightly slower = more gravitas"
echo "  PIPER_NOISE_SCALE=0.45    # less variation = more controlled"
echo "  PIPER_NOISE_W=0.65"
echo ""
echo "Or for edge-tts (recommended, no download needed):"
echo "  TTS_PROVIDER=edge"
echo "  EDGE_TTS_VOICE=en-GB-RyanNeural"
echo "======================================================"
