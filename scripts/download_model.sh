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
if [[ -z "${HF_TOKEN:-}" && -f "$ROOT/.env" ]]; then
  HF_TOKEN="$(grep -E '^HF_TOKEN=' "$ROOT/.env" | cut -d= -f2- || true)"
fi
[[ -n "${HF_TOKEN:-}" ]] && export HF_TOKEN
export HF_HUB_DISABLE_TELEMETRY=1

# Private venv with huggingface_hub (the hf CLI + Python API).
VENV="$ROOT/.venv-tools"
if [[ ! -x "$VENV/bin/hf" ]]; then
  echo "Setting up a small Python environment for downloads (.venv-tools)..."
  python3 -m venv "$VENV"
  "$VENV/bin/pip" -q install --disable-pip-version-check "huggingface_hub>=0.34"
fi

DEST="$ROOT/models/$MODEL_DIR"
mkdir -p "$DEST"
echo "Repo:    $HF_REPO"
echo "Finding files..."
if ! picked="$("$VENV/bin/python" -I "$ROOT/scripts/hf_pick.py" \
      "$HF_REPO" "$HF_INCLUDE_MODEL" "${HF_INCLUDE_MMPROJ:-}")"; then
  echo "Fix HF_INCLUDE_MODEL in $PRESET_FILE (pick a pattern from the list above)." >&2
  exit 1
fi
mapfile -t files <<<"$picked"
(( ${#files[@]} )) || { echo "ERROR: nothing to download" >&2; exit 1; }
printf '  %s\n' "${files[@]}"

# Passing exact file names works the same in old and new versions of the hf CLI.
"$VENV/bin/hf" download "$HF_REPO" "${files[@]}" --local-dir "$DEST"

echo
echo "Downloaded into models/$MODEL_DIR:"
find "$DEST" -name '*.gguf' -printf '  %10s bytes  %P\n' | sort -k3
"$ROOT/scripts/use_model.sh" "$PRESET"
