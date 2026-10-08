# Qwen Workspace: a self-hosted AI chat and agent

A ChatGPT-style chat app that runs entirely on local open-weight models: chat, read uploaded files,
and produce Word documents (PowerPoint, Excel, diagrams, images, reference-file rebranding and web
research come in later phases; see [docs/PLAN.md](docs/PLAN.md)).

It runs on any of these **hardware profiles** ([config/profiles/](config/profiles/)):

| Profile | For | Main model |
|---|---|---|
| `cpu` | any x86-64 PC with 8 GB+ RAM and no GPU, for testing | Qwen3.5-2B (or 4B) on CPU |
| `t4x2` | 2× Tesla T4 (target server) | Qwen3.6-35B-A3B split over both GPUs |
| `t4-split` | 2× Tesla T4, GPU 1 kept for image generation | Qwen3.6-35B-A3B on GPU 0 |

The app and its tools are the same in every profile; only speed and answer quality change.

| Service | What it does | Port |
|---|---|---|
| `llama` | llama.cpp server running Qwen3.6-35B-A3B across both T4s (OpenAI-compatible API, tool calling, vision) | 127.0.0.1:8080 |
| `open-webui` | Chat UI, accounts, history, uploads, RAG | 3000 |
| `docling` | Document extraction with OCR (PDF, Office, HTML, images); off in the `cpu` profile | internal |
| `tools` | FastAPI tool server: `list_uploaded_files`, `read_file`, `create_document`, `append_document_section` | 8001 |

Status per phase: [docs/phases/](docs/phases/).

---

## 1. Quick start on a small PC (no GPU)

Tested target: Lenovo ThinkCentre-class desktop, Intel 6th-gen Core, 4 cores, 8 GB RAM, Ubuntu 22.04/24.04.

```bash
# once: Docker Engine + Compose plugin (https://docs.docker.com/engine/install/ubuntu/)
sudo apt install -y git make python3 openssl
git clone <this repo> qwen-app && cd qwen-app
make check            # should suggest the cpu profile
make init P=cpu       # .env with random secrets, cpu profile, Qwen3.5-2B preset
# if you'll browse from another computer: set TOOLS_PUBLIC_URL=http://<pc-ip>:8001 in .env
make model            # ~2 GB download
make up               # first start pulls ~6 GB of images and takes a while
make bench            # speed + tool-calling + image checks (a few minutes on CPU)
```

Open `http://<pc>:3000`, then follow §4 to set up the agent model.

What to expect on 4 cores / 8 GB:
- Qwen3.5-2B writes roughly 10–20 tokens/s; Qwen3.5-4B is about half that but calls tools more reliably
  (`make use PRESET=qwen35-4b-cpu` after `make model PRESET=qwen35-4b-cpu`).
- The first reply after a long upload can take a minute while the CPU reads the prompt.
- Docling OCR is off to save ~3 GB RAM: text PDFs, Word, PowerPoint and Excel work; scanned PDFs don't.
- Background LLM calls (chat titles, tags, follow-ups) are off so the CPU only answers you.
- Thinking mode is off for these presets (`--reasoning-budget 0` in the preset) to halve response time.

**Add swap on an 8 GB machine** so a memory spike slows things down instead of killing a container:

```bash
sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

Windows: use WSL2 (Ubuntu) with Docker Desktop and run the same commands inside the WSL terminal.

Moving to the T4 server later: copy the repo (and `data/` if you want to keep chats), then
`make profile P=t4x2 && make model && make up`. Chats, users and generated files carry over.

## 2. Requirements for the T4 server

- Ubuntu 22.04 or 24.04, 2× Tesla T4, NVIDIA driver ≥ 550 (≥ 525 minimum)
- Docker Engine with the Compose plugin, and the NVIDIA Container Toolkit
- ~100 GB free disk for models, 32 GB+ RAM recommended
- `uv` (optional, for running tests): `curl -LsSf https://astral.sh/uv/install.sh | sh`

Check the host:

```bash
make check        # CPU, GPUs, driver, docker, GPU access from containers, RAM, disk; suggests a profile
```

## 3. Install on the T4 server

```bash
git clone <this repo> qwen-app && cd qwen-app
make init P=t4x2                           # .env with random secrets + data folders
make model                                 # ~22 GB download into ./models
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

## 4. Set up the agent model in Open WebUI (once)

1. **Admin Settings → External Tools**: "Workspace tools" should be listed (it is added from
   `TOOL_SERVER_CONNECTIONS`). If not, add it: URL `http://tools:8000`, OpenAPI path `openapi.json`,
   auth Bearer with `TOOLS_API_KEY` from `.env`.
2. **Workspace → Models → New model**:
   - Name: `Qwen Agent`; base model: `qwen3.6-35b-a3b` (`qwen3.5-2b` / `qwen3.5-4b` on the cpu profile)
   - System prompt: paste [config/prompts/system.md](config/prompts/system.md)
   - Tools: tick **Workspace tools**
   - Capabilities: tick **Vision** and **File upload**
   - Advanced params → **Function Calling: Native**
3. Optionally make `Qwen Agent` the default model (Admin Settings → Models).

Try: upload a PDF and ask "summarise this file", or ask "write a two-page project brief about X as a Word document".

## 5. Everyday operations

| Task | Command |
|---|---|
| Start / stop | `make up` / `make down` |
| Logs | `make logs S=tools` (or `llama`, `open-webui`, `docling`) |
| Status, GPU memory, container RAM/CPU | `make ps` |
| Switch hardware profile | `make profile P=cpu` (or `t4x2`, `t4-split`), then `make model` and `make up` |
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

- **`t4x2` (layout A)**: the LLM is split across both T4s (`LLM_TENSOR_SPLIT=1,1`).
- **`t4-split` (layout B)**: the LLM is on GPU 0 only, leaving GPU 1 for image generation (Phase 7).
  Its default preset keeps part of the expert weights in system RAM (needs ~24 GB free RAM):
  ```bash
  make profile P=t4-split && make up
  ```

A profile sets `COMPOSE_FILE` and `COMPOSE_PROFILES` in `.env`, so plain `docker compose` commands
use the right files too.

### Pinning versions

`.env` starts with moving tags (`server-cuda`, `main`, `latest`). Once the stack works, pin them so an
update can't break it: `docker image inspect --format '{{index .RepoDigests 0}}' <image>` and put the
`image@sha256:…` value into `LLAMA_IMAGE`, `OPEN_WEBUI_IMAGE` and `DOCLING_IMAGE`.

## 6. Troubleshooting

### CPU-only PC

| Symptom | Fix |
|---|---|
| "request (N tokens) exceeds the available context size" | Uploads plus question are bigger than `LLM_CTX`. See "Context too small" below. |
| A container restarts / "Killed" in logs | Out of RAM. Add swap (§1), use the 2B preset, lower `LLM_CTX` to 4096 in `.env`. |
| Very slow replies | Normal on CPU for long prompts. Use 2B, keep uploads small, check `make ps` for other busy containers. Try `LLM_THREADS=4` (physical cores) in `.env`. |
| `illegal instruction` from llama | CPU lacks instructions the image expects; `make check` shows AVX2 support. Build llama.cpp locally for that CPU. |
| Model writes JSON instead of calling a tool | Small models are less reliable at tool calling: use the 4B preset, and Function Calling = Native on the model. |
| "needs OCR" error on a PDF | Scanned PDFs need Docling, which is off in the cpu profile. Turn it on with `COMPOSE_PROFILES=docling`, `CONTENT_EXTRACTION_ENGINE=docling` and `TOOLS_DOCLING_URL=http://docling:5001` in `.env` if you have 12 GB+ RAM. |

#### Context too small

The model can only read `LLM_CTX` tokens at once (16,384 on the cpu presets). Uploaded documents are
searched and only matching passages are sent, but several large files can still exceed it.
1. In Open WebUI, **Admin Panel → Settings → Documents**: set **Top K** to 3 and make sure
   **Full Context Mode** is off. **Admin Panel → Settings → Interface**: turn off
   **Retrieval Query Generation**. (Open WebUI keeps these in its database, so changes to `.env`
   only apply to a fresh install.)
2. In the chat, click an attached file and choose **Focused Retrieval**, not **Using Entire Document**.
3. Raise `LLM_CTX` in `.env` and run `make up`. The cpu presets use 32768 (2B) and 16384 (4B);
   Qwen3.5 itself supports ~262k. `make doctor` shows the context's memory use ("KV cache" lines)
   and free RAM — raise it while a few GB stay free. On a 4-core CPU a full 32k prompt already
   takes several minutes to read, so bigger windows mostly mean longer waits.

### Tesla T4

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

## 7. Repository layout

```
docker-compose.yml            base stack (t4x2 profile)
docker-compose.gpu-split.yml  t4-split override
docker-compose.cpu.yml        cpu override (no GPU)
.env.example                  all settings
Makefile                      make help
config/profiles/              hardware profiles (cpu, t4x2, t4-split)
config/llama/                 model presets
config/prompts/system.md      agent system prompt
scripts/                      check_host, use_profile, download_model, use_model, bench_llm
services/tools/               FastAPI tool server (app/, tests/, Dockerfile)
docs/PLAN.md                  overall plan and model choices
docs/phases/                  per-phase status, test steps, known issues
```
