# Build plan: self-hosted Qwen agent chat on 2× Tesla T4

Status: **Phases 1–3 built** (see `docs/phases/`); they need a run on the T4 server before Phase 4.

Defaults assumed when the open questions (§7) weren't answered: Ubuntu 22.04/24.04 with driver ≥ 550 and
NVIDIA Container Toolkit (verified by `make check`), LAN-only access, Qwen-Image-Edit-2511, Brave search.
Source brief: the "Self-Hosted AI Agent Chat App" build prompt.

---

## 1. Model check (done 2026-10-08)

Hugging Face is blocked from the build container, so these come from web search
of the HF model pages and the Qwen GitHub. Re-check each on the server with
`huggingface-cli` before downloading.

| Role | Proposed pick | Licence | Notes for T4 |
|---|---|---|---|
| Main LLM | `Qwen/Qwen3.6-35B-A3B` → GGUF `Q4_K_M` + `mmproj` (ggml-org or unsloth build) | Apache 2.0 | MoE, ~3B active. Vision ships as a separate `mmproj` file; it must be loaded with `--mmproj` or image input is silently missing. ~21–22 GB at Q4_K_M, so it is split across both T4s with `--tensor-split`; the rest of the 32 GB goes to KV cache. |
| Alt LLM | `Qwen/Qwen3.8-27B` → Q4 GGUF | **To confirm** (could not open the card) | Dense, native vision-language (image + video in). Q4 ≈ 16–17 GB, so also split. Dense 27B on T4 bandwidth will be noticeably slower than the MoE; benchmark in Phase 1. |
| Image gen | `Qwen/Qwen-Image-2512` → GGUF Q4_K_M (~13 GB) via ComfyUI-GGUF | Apache 2.0 | Fits one T4 for the diffusion model; text encoder + VAE loaded separately/offloaded. |
| Image edit | `Qwen/Qwen-Image-Edit-2511` (GGUF) | Apache 2.0 | Latest **commercially usable** edit model. |
| Excluded | `Qwen-Image-2.1` (Sep 2026, gen+edit in one 7B model) | Qwen Research Licence — **non-commercial** | Excluded by the commercial-use rule. Revisit if the licence changes. |
| Fast fallback | FLUX.1 [schnell] | Apache 2.0 | |
| Embeddings | `Qwen/Qwen3-Embedding-0.6B` | Apache 2.0 | CPU, via Open WebUI's sentence-transformers engine. |
| STT (later) | faster-whisper | MIT | CPU. |

T4 risks to test early:
- Qwen-Image in FP16 (no BF16 on Turing) can produce NaN/black images in some
  setups; Phase 7 starts with a smoke test of FP16 vs. GGUF compute paths.
- FlashAttention: llama.cpp's own `-fa` kernel works on Turing (it is not FA2);
  benchmark with and without it.

---

## 2. GPU layouts (config switch `GPU_LAYOUT`)

**A — `shared` (default):** LLM split across GPU 0+1. Image jobs go through the
GPU scheduler: drain LLM requests → stop `llama` container → run ComfyUI job →
free VRAM → restart `llama` → health check. Cost: ~30–60 s model reload per image
batch (measured in Phase 7). Image jobs are batched in the queue to amortise this.

**B — `split`:** GPU 0 = LLM, GPU 1 = ComfyUI resident. Two options for the LLM:
- B1: a smaller model (~8–14B Q4) fully on GPU 0, as in the brief.
- B2: keep Qwen3.6-35B-A3B but use llama.cpp `--n-cpu-moe N` to keep attention +
  shared weights on GPU 0 and push expert weights to system RAM. Keeps the big
  model's quality at lower speed; needs ≥ 32 GB free RAM. Benchmarked in Phase 1.

---

## 3. Services (`docker compose`)

| Service | Image / build | GPU | Purpose |
|---|---|---|---|
| `llama` | `ghcr.io/ggml-org/llama.cpp:server-cuda` (pinned tag) | 0+1 | OpenAI-compatible API, `--jinja` for tool calling, `--mmproj` for vision |
| `open-webui` | `ghcr.io/open-webui/open-webui` (pinned) | – | UI, auth, history, RAG (Docling + Qwen3-Embedding) |
| `docling` | `docling-serve` (CPU, OCR on) | – | Extraction for Open WebUI and the tool server |
| `tools` | `./services/tools` (FastAPI) | – | OpenAPI tool server: all file/diagram/research/image tools |
| `sandbox` | `./services/sandbox` | – | Runs model Python: `network_mode: none`, CPU/mem/pids limits, per-job tmp dir |
| `renderer` | LibreOffice headless inside `tools` image (one less container) | – | PPTX/DOCX/XLSX → PDF → PNG |
| `comfyui` | `./services/comfyui` (Phase 7) | 1 or 0+1 | Qwen-Image / Edit / FLUX workflows |
| `gpu-scheduler` | module inside `tools` (single asyncio queue + lock) | – | Serialises GPU-heavy jobs, swaps LLM/ComfyUI, logs `nvidia-smi` |

Generated files land in the `data` volume and are served by the tool server at
`/files/{id}/{name}`; tools return that URL so the model can link it in chat.

---

## 4. Directory layout

```
.
├── docker-compose.yml          # base stack
├── docker-compose.gpu-split.yml# override for layout B
├── .env.example                # all config (model paths, ports, API keys)
├── Makefile                    # up / down / logs / bench / test / backup
├── README.md
├── docs/
│   ├── PLAN.md                 # this file
│   └── phases/                 # per-phase "what works / how to test / known issues"
├── models/                     # gitignored; GGUFs + mmproj + ComfyUI weights
├── scripts/
│   ├── download_models.sh      # huggingface-cli downloads, checksums
│   ├── check_host.sh           # driver, CUDA, container toolkit, VRAM
│   ├── bench_llm.py            # tokens/s, TTFT, VRAM per context size
│   └── backup_data.sh
├── config/
│   ├── llama/                  # per-model launch presets (qwen36-35b-a3b.env, qwen38-27b.env…)
│   ├── open-webui/             # tool-server registration, model presets
│   ├── prompts/system.md       # agent system prompt (§7 of the brief)
│   └── brands/                 # brand profiles (yaml + logos)
├── services/
│   ├── tools/
│   │   ├── Dockerfile
│   │   ├── pyproject.toml
│   │   ├── app/
│   │   │   ├── main.py         # FastAPI app, OpenAPI tool routes
│   │   │   ├── config.py       # pydantic-settings from .env
│   │   │   ├── errors.py       # structured ToolError → JSON the model can act on
│   │   │   ├── logging.py      # per-call log: inputs, duration, outcome
│   │   │   ├── storage.py      # file ids, data volume, download URLs
│   │   │   ├── jobs.py         # queue, timeouts, job status polling
│   │   │   ├── gpu.py          # GPU scheduler
│   │   │   ├── readers/        # read_file: docling, tabular, ocr, images
│   │   │   ├── generators/     # docx.py, pptx.py, xlsx.py + specs (pydantic)
│   │   │   ├── templates/      # built-in base .pptx/.docx themes
│   │   │   ├── diagrams/       # mermaid, graphviz, diagrams-lib, svg, charts
│   │   │   ├── reference/      # analyse.py, plan.py, fill.py, verify.py, brands.py, library.py
│   │   │   ├── images/         # comfyui client + workflow JSON
│   │   │   └── research/       # search providers, fetch, deep_research
│   │   └── tests/              # unit tests per tool + fixtures
│   ├── sandbox/
│   └── comfyui/
└── tests/
    ├── integration/            # per-phase end-to-end tests against the running stack
    └── fixtures/               # your three reference files go here (gitignored if confidential)
```

---

## 5. Key design decisions

- **Specs, not coordinates.** `create_presentation`/`create_document`/`create_workbook`
  take pydantic-validated JSON specs; layouts are named (`title`, `two_column`,
  `chart`, `image_right`…) and mapped to template placeholders in code.
- **Small-model-friendly tools.** Few, flat parameters; enums over free text;
  every error returns `{error_code, message, hint}` so the model can retry.
- **Reference mode is code-driven.** Analyse/fill/verify are deterministic Python
  (python-pptx + raw XML for groups/tables/notes/docProps); the model only
  produces the `{shape_id: new_text}` plan and reviews rendered PNGs. A final
  XML grep for old brand strings is a hard gate, not a model judgement.
- **Long jobs are async.** Tools that can exceed ~60 s return a `job_id`; a
  `job_status` tool polls. Keeps Open WebUI from timing out.
- **Open WebUI first.** No custom UI unless a requirement is blocked; I'll flag
  it before building one.

---

## 6. Phase 1 deliverables

1. `scripts/check_host.sh` — verifies driver, CUDA, NVIDIA Container Toolkit, both T4s.
2. `scripts/download_models.sh` — Qwen3.6-35B-A3B Q4_K_M + mmproj.
3. `docker-compose.yml` with `llama` + `open-webui`, model selected via `.env`.
4. `scripts/bench_llm.py` — tokens/s (prompt + generation), TTFT, VRAM per GPU
   at 8k/32k context, tool-call smoke test, image-input smoke test.
5. `docs/phases/phase-1.md` — results, how to test, known issues.

---

## 7. Open questions (need answers before Phase 1)

1. **Host:** Ubuntu version, NVIDIA driver version (`nvidia-smi`), CUDA version,
   Docker + Compose versions, NVIDIA Container Toolkit installed?
2. **CPU / RAM / disk:** cores, system RAM (matters for CPU embeddings, Docling OCR,
   layout B2 expert offload and fast model swaps), free disk for models (~80–100 GB).
3. **Qwen3.8-27B licence:** please confirm on the HF page (I couldn't open it), or
   I check it on the server.
4. **Image edit model:** OK to use Qwen-Image-Edit-2511 (Apache 2.0) and skip
   Qwen-Image-2.1 (non-commercial)?
5. **Search provider** for Phase 8 (Brave / Tavily / SerpAPI / Google PSE)?
6. **Access:** LAN only, or exposed via a domain (needs TLS reverse proxy)?
