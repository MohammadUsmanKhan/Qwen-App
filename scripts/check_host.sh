#!/usr/bin/env bash
# Check the host is ready: OS, NVIDIA driver, both T4s, Docker, Compose,
# NVIDIA Container Toolkit, RAM and disk. Prints PASS/WARN/FAIL per check.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
fails=0
pass() { printf '  \e[32mPASS\e[0m %s\n' "$*"; }
warn() { printf '  \e[33mWARN\e[0m %s\n' "$*"; }
fail() { printf '  \e[31mFAIL\e[0m %s\n' "$*"; fails=$((fails+1)); }

echo "== OS"
if [[ -r /etc/os-release ]]; then . /etc/os-release; pass "$PRETTY_NAME"; else warn "unknown OS"; fi
pass "kernel $(uname -r)"

echo "== NVIDIA driver and GPUs"
if command -v nvidia-smi >/dev/null; then
  drv="$(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -n1)"
  cuda="$(nvidia-smi | grep -oP 'CUDA Version:\s*\K[0-9.]+' || echo '?')"
  pass "driver $drv (max CUDA $cuda)"
  # llama.cpp's CUDA 12 images need driver >= 525; >= 550 recommended.
  major="${drv%%.*}"
  if (( major < 525 )); then fail "driver $drv is too old for CUDA 12 images (need >= 525)";
  elif (( major < 550 )); then warn "driver $drv works, but >= 550 is recommended"; fi
  mapfile -t gpus < <(nvidia-smi --query-gpu=index,name,memory.total,compute_cap --format=csv,noheader)
  for g in "${gpus[@]}"; do echo "       GPU $g"; done
  t4s="$(printf '%s\n' "${gpus[@]}" | grep -c 'T4' || true)"
  if (( t4s >= 2 )); then pass "$t4s × Tesla T4 found"; else warn "expected 2 × T4, found $t4s (${#gpus[@]} GPUs total)"; fi
  if printf '%s\n' "${gpus[@]}" | grep -q '7\.5'; then pass "compute capability 7.5 (Turing): FP16 only, no BF16/FP8"; fi
else
  fail "nvidia-smi not found — install the NVIDIA driver"
fi

echo "== Docker"
if command -v docker >/dev/null; then
  pass "docker $(docker version --format '{{.Server.Version}}' 2>/dev/null || echo '(daemon not reachable)')"
  if docker compose version >/dev/null 2>&1; then pass "$(docker compose version)"; else fail "docker compose plugin missing"; fi
  if docker info 2>/dev/null | grep -qi 'nvidia'; then pass "nvidia runtime registered with docker"; else warn "nvidia runtime not listed in 'docker info'"; fi
  echo "       running a CUDA test container (first run pulls ~100 MB)..."
  if out="$(docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi -L 2>&1)"; then
    pass "GPUs visible inside containers:"; echo "$out" | sed 's/^/         /'
  else
    fail "containers cannot see GPUs — install NVIDIA Container Toolkit:"
    echo "         https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html"
    echo "$out" | tail -n3 | sed 's/^/         /'
  fi
else
  fail "docker not installed"
fi

echo "== CPU / RAM / disk"
pass "$(nproc) CPU threads"
ram_gb="$(awk '/MemTotal/ {printf "%d", $2/1024/1024}' /proc/meminfo)"
if (( ram_gb >= 64 )); then pass "${ram_gb} GB RAM";
elif (( ram_gb >= 32 )); then warn "${ram_gb} GB RAM: fine for layout A; layout B2 (--n-cpu-moe) will be tight";
else warn "${ram_gb} GB RAM: below 32 GB — Docling OCR + embeddings + model loading will be tight"; fi
disk_gb="$(df -BG --output=avail "$ROOT" | tail -n1 | tr -dc '0-9')"
if (( disk_gb >= 120 )); then pass "${disk_gb} GB free disk at $ROOT";
else warn "${disk_gb} GB free disk at $ROOT — models need ~80–100 GB"; fi

echo
if (( fails == 0 )); then echo "Host looks ready."; else echo "$fails check(s) failed."; exit 1; fi
