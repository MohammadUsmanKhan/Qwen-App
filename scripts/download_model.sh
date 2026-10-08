#!/usr/bin/env bash
# Download a preset's GGUF + mmproj from Hugging Face into ./models/<MODEL_DIR>,
# then point .env at it.  Usage: scripts/download_model.sh <preset>
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PRESET="${1:?usage: download_model.sh <preset>   (see config/llama/*.env)}"
PRESET_FILE="$ROOT/config/llama/$PRESET.env"
[[ -f "$PRESET_FILE" ]] || { echo "No preset $PRESET_FILE" >&2; exit 1; }
# shellcheck disable=SC1090
source "$PRESET_FILE"
[[ -f "$ROOT/.env" ]] && HF_TOKEN="${HF_TOKEN:-$(grep -E '^HF_TOKEN=' "$ROOT/.env" | cut -d= -f2- || true)}"
export HF_TOKEN HF_HUB_ENABLE_HF_TRANSFER=1

# Use the hf CLI via uv if present, otherwise a private venv.
if command -v uvx >/dev/null; then
  HF=(uvx --from "huggingface_hub[cli,hf_transfer]" hf)
else
  VENV="$ROOT/.venv-tools"
  [[ -x "$VENV/bin/hf" ]] || { python3 -m venv "$VENV"; "$VENV/bin/pip" -q install "huggingface_hub[cli,hf_transfer]"; }
  HF=("$VENV/bin/hf")
fi

DEST="$ROOT/models/$MODEL_DIR"
mkdir -p "$DEST"
echo "Repo:    $HF_REPO"
echo "Listing files that match the preset patterns..."
patterns=("$HF_INCLUDE_MODEL")
[[ -n "${HF_INCLUDE_MMPROJ:-}" ]] && patterns+=("$HF_INCLUDE_MMPROJ")

"${HF[@]}" download "$HF_REPO" --include "${patterns[@]}" --local-dir "$DEST"

echo
echo "Downloaded into models/$MODEL_DIR:"
find "$DEST" -name '*.gguf' -printf '  %10s bytes  %P\n' | sort -k3
if ! find "$DEST" -name '*.gguf' ! -name 'mmproj*' | grep -q .; then
  echo "ERROR: pattern '$HF_INCLUDE_MODEL' matched no model file in $HF_REPO." >&2
  echo "Check https://huggingface.co/$HF_REPO/tree/main and fix $PRESET_FILE" >&2
  exit 1
fi
"$ROOT/scripts/use_model.sh" "$PRESET"
