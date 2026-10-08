#!/usr/bin/env bash
# Check the host is ready and suggest a hardware profile.
# Works with or without NVIDIA GPUs. Prints PASS/WARN/FAIL per check.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
fails=0
pass() { printf '  \e[32mPASS\e[0m %s\n' "$*"; }
warn() { printf '  \e[33mWARN\e[0m %s\n' "$*"; }
fail() { printf '  \e[31mFAIL\e[0m %s\n' "$*"; fails=$((fails+1)); }

echo "== OS"
if [[ -r /etc/os-release ]]; then . /etc/os-release; pass "$PRETTY_NAME"; else warn "unknown OS"; fi
pass "kernel $(uname -r), $(uname -m)"
[[ "$(uname -m)" == "x86_64" ]] || warn "not x86-64: the llama.cpp images used here are built for x86-64"

echo "== CPU"
cpu_model="$(awk -F': ' '/model name/ {print $2; exit}' /proc/cpuinfo)"
threads="$(nproc)"
pass "${cpu_model:-unknown CPU}, $threads threads"
flags="$(grep -m1 '^flags' /proc/cpuinfo)"
if grep -qw avx2 <<<"$flags"; then pass "AVX2 supported (fast llama.cpp CPU kernels)";
elif grep -qw avx <<<"$flags"; then warn "AVX but no AVX2: CPU inference will be slow";
else warn "no AVX: CPU inference will be very slow"; fi

echo "== NVIDIA GPUs"
gpu_count=0
if command -v nvidia-smi >/dev/null && nvidia-smi -L >/dev/null 2>&1; then
  drv="$(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -n1)"
  cuda="$(nvidia-smi | grep -oP 'CUDA Version:\s*\K[0-9.]+' || echo '?')"
  pass "driver $drv (max CUDA $cuda)"
  major="${drv%%.*}"
  if (( major < 525 )); then fail "driver $drv is too old for CUDA 12 images (need >= 525)";
  elif (( major < 550 )); then warn "driver $drv works, but >= 550 is recommended"; fi
  mapfile -t gpus < <(nvidia-smi --query-gpu=index,name,memory.total,compute_cap --format=csv,noheader)
  gpu_count="${#gpus[@]}"
  for g in "${gpus[@]}"; do echo "       GPU $g"; done
  t4s="$(printf '%s\n' "${gpus[@]}" | grep -c 'T4' || true)"
  if (( t4s >= 2 )); then pass "$t4s × Tesla T4 found"; fi
  if printf '%s\n' "${gpus[@]}" | grep -q '7\.5'; then pass "compute capability 7.5 (Turing): FP16 only, no BF16/FP8"; fi
else
  warn "no NVIDIA GPU found — use the CPU-only profile (make profile P=cpu)"
fi

echo "== Docker"
if command -v docker >/dev/null; then
  if server="$(docker version --format '{{.Server.Version}}' 2>/dev/null)"; then pass "docker $server";
  else fail "docker daemon not reachable (is it running? is your user in the 'docker' group?)"; fi
  if docker compose version >/dev/null 2>&1; then pass "$(docker compose version)"; else fail "docker compose plugin missing"; fi
  if (( gpu_count > 0 )); then
    echo "       running a CUDA test container (first run pulls ~100 MB)..."
    if out="$(docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi -L 2>&1)"; then
      pass "GPUs visible inside containers:"; echo "$out" | sed 's/^/         /'
    else
      fail "containers cannot see GPUs — install NVIDIA Container Toolkit:"
      echo "         https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html"
      echo "$out" | tail -n3 | sed 's/^/         /'
    fi
  fi
else
  fail "docker not installed: https://docs.docker.com/engine/install/ubuntu/"
fi

echo "== RAM / disk"
ram_gb="$(awk '/MemTotal/ {printf "%.0f", $2/1024/1024}' /proc/meminfo)"
avail_gb="$(awk '/MemAvailable/ {printf "%.1f", $2/1024/1024}' /proc/meminfo)"
swap_gb="$(awk '/SwapTotal/ {printf "%.0f", $2/1024/1024}' /proc/meminfo)"
disk_gb="$(df -BG --output=avail "$ROOT" | tail -n1 | tr -dc '0-9')"
if (( gpu_count > 0 )); then
  if (( ram_gb >= 32 )); then pass "${ram_gb} GB RAM (${avail_gb} GB free)";
  else warn "${ram_gb} GB RAM: 32 GB+ recommended with the T4 profiles (Docling OCR, embeddings, model loading)"; fi
  if (( disk_gb >= 120 )); then pass "${disk_gb} GB free disk"; else warn "${disk_gb} GB free disk — the T4 models need ~80–100 GB"; fi
else
  if (( ram_gb >= 16 )); then pass "${ram_gb} GB RAM (${avail_gb} GB free): CPU profile can use the 4B model";
  elif (( ram_gb >= 7 )); then pass "${ram_gb} GB RAM (${avail_gb} GB free): CPU profile with the 2B model (4B also fits, slower)";
  else fail "${ram_gb} GB RAM: at least 8 GB is needed even for the CPU profile"; fi
  (( ram_gb >= 16 || swap_gb >= 2 )) || warn "only ${swap_gb} GB swap: add 4 GB of swap as a safety net on an 8 GB machine (see README)"
  if (( disk_gb >= 25 )); then pass "${disk_gb} GB free disk"; else warn "${disk_gb} GB free disk — the CPU profile needs ~15–20 GB (images + model)"; fi
fi

echo
if (( gpu_count >= 2 )); then echo "Suggested profile: t4x2   (make profile P=t4x2)";
elif (( gpu_count == 1 )); then echo "Suggested profile: t4-split   (make profile P=t4-split)";
else echo "Suggested profile: cpu   (make profile P=cpu)"; fi
if (( fails == 0 )); then echo "Host looks ready."; else echo "$fails check(s) failed."; exit 1; fi
