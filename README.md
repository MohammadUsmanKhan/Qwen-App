# Qwen Workspace: a self-hosted AI chat and agent on 2× Tesla T4

A ChatGPT-style chat app that runs entirely on local open-weight models: chat, read uploaded files,
and produce Word documents (PowerPoint, Excel, diagrams, images, reference-file rebranding and web
research come in later phases; see [docs/PLAN.md](docs/PLAN.md)).

| Service | What it does | Port |
|---|---|---|
| `llama` | llama.cpp server running Qwen3.6-35B-A3B across both T4s (OpenAI-compatible API, tool calling, vision) | 127.0.0.1:8080 |
| `open-webui` | Chat UI, accounts, history, uploads, RAG | 3000 |
| `docling` | Document extraction with OCR (PDF, Office, HTML, images) | internal |
| `tools` | FastAPI tool server: `list_uploaded_files`, `read_file`, `create_document`, `append_document_section` | 8001 |

Status per phase: [docs/phases/](docs/phases/).

---

## 1. Requirements

- Ubuntu 22.04 or 24.04, 2× Tesla T4, NVIDIA driver ≥ 550 (≥ 525 minimum)
- Docker Engine with the Compose plugin, and the NVIDIA Container Toolkit
- ~100 GB free disk for models, 32 GB+ RAM recommended
- `uv` (optional, for running tests): `curl -LsSf https://astral.sh/uv/install.sh | sh`

Check the host:

```bash
make check        # driver, both T4s, docker, compose, GPU access from containers, RAM, disk
```

## 2. Install

```bash
git clone <this repo> qwen-app && cd qwen-app
make init                                  # .env with random secrets + data folders
make model PRESET=qwen36-35b-a3b           # ~22 GB download into ./models
```

Edit `.env`:
- `TOOLS_PUBLIC_URL`: the address **users' browsers** use to reach port 8001, e.g. `http://192.168.1.50:8001`.
  Download links in chat point here, so `localhost` only works on the server itself.

Start:

```bash
make up           # builds the tool server, starts everything
make logs S=llama # wait for "server is listening" (loading takes 1–3 minutes)
make bench        # speed, VRAM, tool-calling and image-input checks
```

Open `http://<server>:3000`. **The first account you create becomes the admin.** Then set
`ENABLE_SIGNUP=false` in `.env` (or turn sign-up off in Admin Settings) and run `make up`.

## 3. Set up the agent model in Open WebUI (once)

1. **Admin Settings → External Tools**: "Workspace tools" should be listed (it is added from
   `TOOL_SERVER_CONNECTIONS`). If not, add it: URL `http://tools:8000`, OpenAPI path `openapi.json`,
   auth Bearer with `TOOLS_API_KEY` from `.env`.
2. **Workspace → Models → New model**:
   - Name: `Qwen Agent`; base model: `qwen3.6-35b-a3b`
   - System prompt: paste [config/prompts/system.md](config/prompts/system.md)
   - Tools: tick **Workspace tools**
   - Capabilities: tick **Vision** and **File upload**
   - Advanced params → **Function Calling: Native**
3. Optionally make `Qwen Agent` the default model (Admin Settings → Models).

Try: upload a PDF and ask "summarise this file", or ask "write a two-page project brief about X as a Word document".

## 4. Everyday operations

| Task | Command |
|---|---|
| Start / stop | `make up` / `make down` |
| Logs | `make logs S=tools` (or `llama`, `open-webui`, `docling`) |
| Status + GPU memory | `make ps` |
| Tool call log | `data/tools/logs/tool_calls.jsonl` (one JSON line per call: tool, user, args, duration, error) |
| Run tests | `make test` |

### Swapping the main model

Presets live in [config/llama/](config/llama/). Each one says where to download the model from and how to run it.

```bash
make model PRESET=qwen38-27b      # download
make use PRESET=qwen38-27b        # point .env at it and restart llama
make bench
```

In Open WebUI, change the `Qwen Agent` model's base model to the new alias. To add a model, copy a preset and
edit `HF_REPO`, the file patterns, `MODEL_DIR` and `LLM_ALIAS`.

### GPU layouts

- **Layout A (default)**: the LLM is split across both T4s (`LLM_TENSOR_SPLIT=1,1`).
- **Layout B**: the LLM is on GPU 0 only, leaving GPU 1 for image generation (Phase 7):
  ```bash
  make use PRESET=qwen36-35b-a3b-cpumoe   # experts partly in system RAM (needs ~24 GB free RAM)
  make up LAYOUT=split
  ```

### Pinning versions

`.env` starts with moving tags (`server-cuda`, `main`, `latest`). Once the stack works, pin them so an
update can't break it: `docker image inspect --format '{{index .RepoDigests 0}}' <image>` and put the
`image@sha256:…` value into `LLAMA_IMAGE`, `OPEN_WEBUI_IMAGE` and `DOCLING_IMAGE`.

## 5. Troubleshooting (T4-specific)

| Symptom | Fix |
|---|---|
| `CUDA error: no kernel image is available` | The llama.cpp image wasn't built for compute 7.5. Use a newer `server-cuda` tag, or build llama.cpp with `CMAKE_CUDA_ARCHITECTURES=75`. |
| `CUDA driver version is insufficient` | The image needs a newer driver than the host has. Upgrade the driver (≥ 550) or use an older image tag. |
| Out of memory while loading | Lower `LLM_CTX` or `LLM_PARALLEL`, or keep `q8_0` KV cache. For layout B raise `--n-cpu-moe`. |
| Garbage output with `-fa on` | Set `LLM_FLASH_ATTN=off`, then compare speed with `make bench`. |
| Model ignores images | `mmproj` not loaded: check `LLM_MMPROJ_FILE` in `.env` and the llama log for `mmproj`; tick Vision on the model in Open WebUI. |
| Model answers instead of calling tools | Set Function Calling = Native on the model; check `make bench` passes "tool calling". |
| `user_unknown` error from tools | Open WebUI isn't forwarding user headers: `ENABLE_FORWARD_USER_INFO_HEADERS=true`. |
| `uploads_unavailable` error from tools | `./data/open-webui` isn't mounted into `tools`, or Open WebUI uses S3/Postgres storage (unsupported for now). |
| Download link doesn't open | `TOOLS_PUBLIC_URL` must be reachable from the browser; port 8001 must be open in the firewall. |
| Env changes to Open WebUI have no effect | Open WebUI saves most settings in its database on first start; change them in Admin Settings. |

## 6. Repository layout

```
docker-compose.yml            base stack (layout A)
docker-compose.gpu-split.yml  layout B override
.env.example                  all settings
Makefile                      make help
config/llama/                 model presets
config/prompts/system.md      agent system prompt
scripts/                      check_host, download_model, use_model, bench_llm
services/tools/               FastAPI tool server (app/, tests/, Dockerfile)
docs/PLAN.md                  overall plan and model choices
docs/phases/                  per-phase status, test steps, known issues
```
