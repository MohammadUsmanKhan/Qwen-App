#!/usr/bin/env bash
# Collect everything needed to debug a stuck or failing stack, in one paste.
# Usage: make doctor   (or scripts/doctor.sh > doctor.txt)
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 1
env_get() { grep -E "^$1=" .env 2>/dev/null | cut -d= -f2- ; }
PORT="$(env_get LLM_PORT)"; PORT="${PORT:-8080}"
section() { printf '\n===== %s =====\n' "$*"; }

section "profile / model"
grep -E '^(HW_PROFILE|COMPOSE_FILE|COMPOSE_PROFILES|LLM_PRESET|LLM_ALIAS|LLM_MODEL_FILE|LLM_MMPROJ_FILE|LLM_CTX|LLM_THREADS|LLM_EXTRA_ARGS)=' .env
for f in "models/$(env_get LLM_MODEL_FILE)" "models/$(env_get LLM_MMPROJ_FILE)"; do
  [[ "$f" == "models/" ]] && continue
  if [[ -f "$f" ]]; then echo "OK      $(du -h "$f" | cut -f1)  $f"; else echo "MISSING $f"; fi
done

section "memory"
free -h
section "containers"
docker compose ps -a
docker stats --no-stream --format 'table {{.Name}}\t{{.MemUsage}}\t{{.CPUPerc}}'
section "llama image"
docker compose images llama 2>/dev/null

section "llama server health"
curl -sS -m 5 "http://127.0.0.1:$PORT/health"; echo
curl -sS -m 5 "http://127.0.0.1:$PORT/v1/models" | head -c 400; echo

section "direct test: 'Say hi' straight to llama.cpp (max 3 min)"
start=$(date +%s)
curl -sS -m 180 "http://127.0.0.1:$PORT/v1/chat/completions" -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Say hi in five words."}],"max_tokens":40,"temperature":0}' \
  | python3 -c '
import json, sys
try:
    r = json.load(sys.stdin)
except Exception as e:
    print("no JSON reply:", e); sys.exit()
if "error" in r:
    print("ERROR:", r["error"]); sys.exit()
m = r["choices"][0]["message"]
t = r.get("timings", {})
print("content:  ", repr(m.get("content")))
print("reasoning:", repr((m.get("reasoning_content") or "")[:200]))
print("finish:   ", r["choices"][0].get("finish_reason"))
print("speed:     prompt %.1f tok/s, generation %.1f tok/s" % (t.get("prompt_per_second", 0), t.get("predicted_per_second", 0)))
'
echo "took $(( $(date +%s) - start ))s"

section "llama context and memory (from startup log)"
docker compose logs --no-color llama 2>&1 | grep -iE 'n_ctx|kv.?cache|KV self|recurrent|buffer size|model size|n_ctx_train' | tail -n 15

section "llama logs (last 60 lines)"
docker compose logs --no-color --tail=60 llama 2>&1
section "open-webui logs (errors, last 30)"
docker compose logs --no-color --tail=400 open-webui 2>&1 | grep -iE 'error|exception|traceback|timeout|refused' | tail -n 30
section "tools logs (last 15 lines)"
docker compose logs --no-color --tail=15 tools 2>&1
section "kernel out-of-memory kills"
(dmesg 2>/dev/null || sudo -n dmesg 2>/dev/null) | grep -iE 'out of memory|oom-kill|killed process' | tail -n 5 \
  || echo "(no access to dmesg; run 'sudo dmesg | grep -i oom' to check)"
