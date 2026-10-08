# Phase 1: Foundation

**Status: built, not yet run on the T4 server.** The build environment has no GPU or Docker daemon, so
everything below was checked statically (compose validated, scripts tested against a mock llama-server).

## What's included
- `docker-compose.yml`: llama.cpp `server-cuda` split across both T4s, Open WebUI connected to it.
- Model presets in `config/llama/`: Qwen3.6-35B-A3B (default), Qwen3.6-35B-A3B with `--n-cpu-moe` for layout B,
  Qwen3.8-27B. Swapping is `make model` + `make use`, no code changes.
- llama-server settings: `--jinja` (tool calling via the model's chat template), `--mmproj` (vision),
  `-fa on` (llama.cpp's own flash attention, which runs on Turing), q8_0 KV cache, 32k context shared by
  2 parallel slots, `--metrics`.
- `scripts/check_host.sh`: driver, T4s, compute capability, Docker, Compose, GPU access from containers, RAM, disk.
- `scripts/download_model.sh`: downloads by pattern from Hugging Face and writes the real filenames into `.env`.
- `scripts/bench_llm.py`: prompt and generation tokens/s at 512 / 4k / 16k tokens, time to first token,
  VRAM per GPU, plus tool-calling and image-input pass/fail checks.
- Hardware profiles (`config/profiles/`): `cpu` for a GPU-less test PC, `t4x2` and `t4-split` for the
  server. `make check` suggests one; `make init P=...` / `make profile P=...` applies it.
  The `cpu` profile uses the llama.cpp CPU image, Qwen3.5-2B/4B (with vision), no Docling, MiniLM
  embeddings and no background LLM calls, so the whole app fits in 8 GB RAM.

## How to test

On the small PC first (no GPU):
```bash
make check                          # should suggest "cpu"
make init P=cpu && make model && make up
make bench                          # paste the output back to me
```
On the T4 server:
```bash
make check
make init P=t4x2 && make model
make up && make logs S=llama        # wait until it is listening
make bench                          # paste the output back to me
```
Then open `http://<server>:3000`, create the admin account, and chat with `qwen3.6-35b-a3b`.

## Known issues / to confirm
- Qwen3.5-2B/4B GGUF repos (`unsloth/Qwen3.5-*-GGUF`) and their `mmproj-F16.gguf` names are from
  search results; if a pattern matches nothing the download script says so.
- Small models call tools less reliably than the 35B; on the CPU PC, failures to call a tool are a model
  limit, not necessarily a bug. Try the 4B preset before judging a tool.
- Hugging Face file patterns (`*UD-Q4_K_M*.gguf`, `mmproj-F16.gguf`) are from the repo listings as I
  could see them; the download script stops with a clear message if a pattern matches nothing.
- The Qwen3.8-27B licence still needs checking on its model card.
- Images use moving tags until you pin them (README → Pinning versions).
- Expected speed is unknown until `make bench` runs; it decides between layout A and B2.
