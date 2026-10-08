#!/usr/bin/env bash
# Switch .env to a hardware profile from config/profiles/ (t4x2, t4-split, cpu).
# Usage: scripts/use_profile.sh <profile>
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/scripts/lib.sh"
PROFILE="${1:-}"
if [[ -z "$PROFILE" || ! -f "$ROOT/config/profiles/$PROFILE.env" ]]; then
  echo "usage: use_profile.sh <profile>   available:" >&2
  for f in "$ROOT"/config/profiles/*.env; do
    # shellcheck disable=SC1090
    (source "$f"; printf '  %-10s %s\n' "$(basename "$f" .env)" "$DESCRIPTION") >&2
  done
  exit 1
fi
ENV_FILE="$ROOT/.env"
[[ -f "$ENV_FILE" ]] || { echo "No .env yet — run: make init" >&2; exit 1; }

# shellcheck disable=SC1090
source "$ROOT/config/profiles/$PROFILE.env"
set_var "$ENV_FILE" HW_PROFILE "$PROFILE"
for key in COMPOSE_FILE COMPOSE_PROFILES CONTENT_EXTRACTION_ENGINE TOOLS_DOCLING_URL \
           RAG_EMBEDDING_MODEL ENABLE_BACKGROUND_TASKS RAG_TOP_K; do
  set_var "$ENV_FILE" "$key" "${!key:-}"
done
echo "Profile: $PROFILE — $DESCRIPTION"

# Each profile has a default model preset; pick another with `make use PRESET=...`.
"$ROOT/scripts/use_model.sh" "$DEFAULT_PRESET" | grep -v '^Apply with' || true
# shellcheck disable=SC1090
model_dir="$(source "$ROOT/config/llama/$DEFAULT_PRESET.env"; echo "$MODEL_DIR")"
if ! find "$ROOT/models/$model_dir" -name '*.gguf' 2>/dev/null | grep -q .; then
  echo "Next: make model     (downloads $DEFAULT_PRESET)"
fi
echo "Apply with: make up"
