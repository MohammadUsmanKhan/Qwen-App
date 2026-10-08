# llama.cpp presets

Each `*.env` file describes one main-LLM setup: where to download it from and the
`llama-server` settings to run it with.

    scripts/download_model.sh <preset>   # fetch weights into ./models/<MODEL_DIR>
    scripts/use_model.sh <preset>        # write the LLM_* settings into .env
    docker compose up -d llama           # restart with the new model

Each `HF_INCLUDE_*` value is a space-separated list of patterns tried in order; the first
one that matches a file in the repo is downloaded. The download script prints what it picked,
and if nothing matches it lists the repo's GGUF files so you can fix `HF_INCLUDE_*`.

To add a model: copy a preset, change `HF_REPO`, the patterns, `MODEL_DIR` and
`LLM_ALIAS`. Leave `HF_INCLUDE_MMPROJ` empty for text-only models.
