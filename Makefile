# Common operations. Run `make help` for the list.
SHELL := /bin/bash
COMPOSE := docker compose
ifeq ($(LAYOUT),split)
COMPOSE := docker compose -f docker-compose.yml -f docker-compose.gpu-split.yml
endif

.PHONY: help init check model use up down restart logs ps bench test lint

help:  ## show this help
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS=":.*## "} {printf "  make %-10s %s\n", $$1, $$2}'

init:  ## create .env with random secrets and the data folders
	@if [ -f .env ]; then echo ".env exists, leaving it alone"; else \
	  cp .env.example .env; \
	  for k in WEBUI_SECRET_KEY TOOLS_API_KEY TOOLS_SIGNING_KEY; do \
	    sed -i "s|^$$k=.*|$$k=$$(openssl rand -hex 32)|" .env; done; \
	  echo "created .env with random secrets"; fi
	@mkdir -p data/open-webui data/tools models

check:  ## check driver, GPUs, docker and the NVIDIA container toolkit
	scripts/check_host.sh

model:  ## download a model preset: make model PRESET=qwen36-35b-a3b
	scripts/download_model.sh $(or $(PRESET),qwen36-35b-a3b)

use:  ## switch .env to a downloaded preset: make use PRESET=qwen38-27b
	scripts/use_model.sh $(PRESET) && $(COMPOSE) up -d llama

up:  ## start the stack (LAYOUT=split for the GPU-split layout)
	$(COMPOSE) up -d --build

down:  ## stop the stack
	$(COMPOSE) down

restart:  ## restart one service: make restart S=tools
	$(COMPOSE) restart $(S)

logs:  ## follow logs: make logs S=llama
	$(COMPOSE) logs -f --tail=200 $(S)

ps:  ## service status and GPU memory
	$(COMPOSE) ps
	@nvidia-smi --query-gpu=index,name,memory.used,memory.total,utilization.gpu --format=csv 2>/dev/null || true

bench:  ## benchmark the LLM (speed, VRAM, tool calling, vision)
	python3 scripts/bench_llm.py --json data/bench-$$(date +%Y%m%d-%H%M).json

test:  ## run the tool server's unit tests (needs uv)
	cd services/tools && uv run --extra dev pytest -q

lint:  ## ruff + mypy on the tool server
	cd services/tools && uv run --extra dev ruff check . && uv run --extra dev mypy app
