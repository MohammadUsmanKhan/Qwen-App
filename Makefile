# Common operations. Run `make help` for the list.
SHELL := /bin/bash
# Compose files and optional services come from COMPOSE_FILE / COMPOSE_PROFILES in .env
# (set by `make profile`), so plain `docker compose ...` commands work too.
COMPOSE := docker compose

.PHONY: help init profile check model use up down restart logs ps bench test lint

help:  ## show this help
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS=":.*## "} {printf "  make %-10s %s\n", $$1, $$2}'

init:  ## create .env with random secrets: make init P=cpu (or t4x2, t4-split)
	@mkdir -p data/open-webui data/tools models
	@if [ -f .env ]; then \
	  echo ".env exists, keeping its secrets"; \
	  if [ -n "$(P)" ]; then scripts/use_profile.sh $(P); fi; \
	else \
	  cp .env.example .env; \
	  for k in WEBUI_SECRET_KEY TOOLS_API_KEY TOOLS_SIGNING_KEY; do \
	    sed -i "s|^$$k=.*|$$k=$$(openssl rand -hex 32)|" .env; done; \
	  echo "created .env with random secrets"; \
	  scripts/use_profile.sh $(or $(P),t4x2); \
	fi

profile:  ## switch hardware profile: make profile P=cpu (or t4x2, t4-split)
	@scripts/use_profile.sh $(P)

check:  ## check driver, GPUs, docker and the NVIDIA container toolkit
	scripts/check_host.sh

model:  ## download the profile's model, or one preset: make model PRESET=qwen35-4b-cpu
	scripts/download_model.sh $(or $(PRESET),$$(grep -E '^LLM_PRESET=' .env | cut -d= -f2))

use:  ## switch .env to a downloaded preset: make use PRESET=qwen38-27b
	scripts/use_model.sh $(PRESET) && $(COMPOSE) up -d llama

up:  ## start the stack for the current profile
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
	@docker stats --no-stream --format 'table {{.Name}}\t{{.MemUsage}}\t{{.CPUPerc}}' 2>/dev/null || true

bench:  ## benchmark the LLM (speed, VRAM, tool calling, vision)
	python3 scripts/bench_llm.py --json data/bench-$$(date +%Y%m%d-%H%M).json

test:  ## run the tool server's unit tests (needs uv)
	cd services/tools && uv run --extra dev pytest -q

lint:  ## ruff + mypy on the tool server
	cd services/tools && uv run --extra dev ruff check . && uv run --extra dev mypy app
