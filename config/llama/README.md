# llama.cpp presets

Each `*.env` file describes one main-LLM setup: where to download it from and the
`llama-server` settings to run it with.

    scripts/download_model.sh <preset>   # fetch weights into ./models/<MODEL_DIR>
    scripts/use_model.sh <preset>        # write the LLM_* settings into .env
    docker compose up -d llama           # restart with the new model

Repo names and file patterns are best guesses from the Hugging Face listings;
the download script prints what it actually matched. If a pattern matches nothing,
open the repo's "Files" tab and fix `HF_INCLUDE_*`.

To add a model: copy a preset, change `HF_REPO`, the patterns, `MODEL_DIR` and
`LLM_ALIAS`. Leave `HF_INCLUDE_MMPROJ` empty for text-only models.
