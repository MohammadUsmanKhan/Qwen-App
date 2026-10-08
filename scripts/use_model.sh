#!/usr/bin/env bash
# Point .env at a model preset from config/llama/ and resolve the downloaded files.
# Usage: scripts/use_model.sh <preset>
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PRESET="${1:?usage: use_model.sh <preset>   (see config/llama/*.env)}"
PRESET_FILE="$ROOT/config/llama/$PRESET.env"
ENV_FILE="$ROOT/.env"
[[ -f "$PRESET_FILE" ]] || { echo "No preset $PRESET_FILE" >&2; exit 1; }
[[ -f "$ENV_FILE" ]] || cp "$ROOT/.env.example" "$ENV_FILE"

# shellcheck disable=SC1090
source "$PRESET_FILE"
MODEL_PATH="$ROOT/models/$MODEL_DIR"

# First shard of the main model (split GGUFs are named *-00001-of-0000N.gguf).
model_file="$(find "$MODEL_PATH" -name '*.gguf' ! -name 'mmproj*' 2>/dev/null \
  | grep -v -E -- '-0000[2-9]-of-|-000[1-9][0-9]-of-' | sort | head -n1 || true)"
mmproj_file=""
if [[ -n "${HF_INCLUDE_MMPROJ:-}" ]]; then
  mmproj_file="$(find "$MODEL_PATH" -name 'mmproj*.gguf' 2>/dev/null | sort | head -n1 || true)"
fi
if [[ -z "$model_file" ]]; then
  echo "WARNING: no .gguf found under models/$MODEL_DIR — run scripts/download_model.sh $PRESET" >&2
  model_rel="$MODEL_DIR/MISSING.gguf"
else
  model_rel="${model_file#"$ROOT/models/"}"
fi
mmproj_rel=""
[[ -n "$mmproj_file" ]] && mmproj_rel="${mmproj_file#"$ROOT/models/"}"

set_var() {  # set_var KEY VALUE — replace or append in .env
  local key="$1" val="$2" tmp
  tmp="$(mktemp)"
  if grep -q "^${key}=" "$ENV_FILE"; then
    awk -v k="$key" -v v="$val" 'BEGIN{FS=OFS="="} $1==k {print k "=" v; next} {print}' "$ENV_FILE" > "$tmp"
  else
    cat "$ENV_FILE" > "$tmp"; echo "${key}=${val}" >> "$tmp"
  fi
  cat "$tmp" > "$ENV_FILE"; rm -f "$tmp"
}

set_var LLM_PRESET "$PRESET"
set_var LLM_MODEL_FILE "$model_rel"
set_var LLM_MMPROJ_FILE "$mmproj_rel"
for key in LLM_ALIAS LLM_CTX LLM_PARALLEL LLM_TENSOR_SPLIT LLM_N_GPU_LAYERS \
           LLM_FLASH_ATTN LLM_CACHE_TYPE_K LLM_CACHE_TYPE_V LLM_EXTRA_ARGS; do
  set_var "$key" "${!key:-}"
done

echo "Preset:  $PRESET"
echo "Model:   models/$model_rel"
if [[ -n "$mmproj_rel" ]]; then echo "mmproj:  models/$mmproj_rel"; else echo "mmproj:  (none — no image input)"; fi
echo "Apply with: docker compose up -d llama"
