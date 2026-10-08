#!/usr/bin/env python3
"""Benchmark and smoke-test the llama.cpp server.

Measures prompt-processing and generation speed at several prompt sizes, time to
first token, and VRAM per GPU; then checks that tool calling and image input work.
Standard library only, so it runs on the host without installing anything.

    python3 scripts/bench_llm.py                      # http://127.0.0.1:8080
    python3 scripts/bench_llm.py --url http://host:8080 --sizes 512,8000,24000
    python3 scripts/bench_llm.py --json results.json
"""

from __future__ import annotations

import argparse
import base64
import json
import shutil
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zlib
from typing import Any

FILLER = (
    "The quarterly report covers revenue, operating costs, staffing, and the "
    "outlook for the next two quarters across all regional offices. "
)


def post(url: str, body: dict[str, Any], timeout: float = 600) -> dict[str, Any]:
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def get(url: str, timeout: float = 10) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read())


def vram() -> list[dict[str, Any]]:
    if not shutil.which("nvidia-smi"):
        return []
    out = subprocess.run(
        ["nvidia-smi", "--query-gpu=index,name,memory.used,memory.total,utilization.gpu",
         "--format=csv,noheader,nounits"],
        capture_output=True, text=True, check=False,
    ).stdout
    gpus = []
    for line in out.strip().splitlines():
        idx, name, used, total, util = (p.strip() for p in line.split(","))
        gpus.append({"gpu": int(idx), "name": name, "used_mib": int(used),
                     "total_mib": int(total), "util_pct": int(util)})
    return gpus


def tokenize_len(base: str, text: str) -> int:
    return len(post(f"{base}/tokenize", {"content": text})["tokens"])


def make_prompt(base: str, target_tokens: int) -> str:
    per = max(1, tokenize_len(base, FILLER))
    return FILLER * max(1, target_tokens // per)


def stream_ttft(base: str, model: str, prompt: str, max_tokens: int) -> float:
    """Seconds until the first streamed content (or reasoning) token arrives."""
    body = {"model": model, "stream": True, "max_tokens": max_tokens, "temperature": 0,
            "messages": [{"role": "user", "content": prompt}]}
    req = urllib.request.Request(f"{base}/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    start = time.perf_counter()
    with urllib.request.urlopen(req, timeout=600) as resp:
        for raw in resp:
            line = raw.decode().strip()
            if not line.startswith("data:") or line.endswith("[DONE]"):
                continue
            delta = json.loads(line[5:])["choices"][0].get("delta", {})
            if delta.get("content") or delta.get("reasoning_content"):
                return time.perf_counter() - start
    return float("nan")


def bench_size(base: str, model: str, size: int, gen: int) -> dict[str, Any]:
    prompt = make_prompt(base, size) + "\nSummarise the above in one sentence."
    # Unique prefix defeats the prompt cache between runs.
    prompt = f"[run {time.time_ns()}]\n" + prompt
    ttft = stream_ttft(base, model, prompt, max_tokens=8)
    prompt = f"[run {time.time_ns()}]\n" + prompt
    res = post(f"{base}/v1/chat/completions", {
        "model": model, "max_tokens": gen, "temperature": 0,
        "messages": [{"role": "user", "content": prompt}],
    })
    t = res.get("timings", {})
    return {
        "prompt_tokens": t.get("prompt_n"),
        "prompt_tok_s": round(t.get("prompt_per_second", 0), 1),
        "gen_tokens": t.get("predicted_n"),
        "gen_tok_s": round(t.get("predicted_per_second", 0), 1),
        "ttft_s": round(ttft, 2),
        "vram": vram(),
    }


def check_tool_call(base: str, model: str) -> tuple[bool, str]:
    tools = [{
        "type": "function",
        "function": {
            "name": "create_document",
            "description": "Create a Word document from a title and a list of headings.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "headings": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["title", "headings"],
            },
        },
    }]
    res = post(f"{base}/v1/chat/completions", {
        "model": model, "temperature": 0, "max_tokens": 2048, "tools": tools,
        "messages": [{"role": "user", "content":
                      "Make me a Word document titled 'Site Survey' with sections Scope, Findings, Next Steps."}],
    })
    msg = res["choices"][0]["message"]
    calls = msg.get("tool_calls") or []
    if not calls:
        return False, f"no tool_calls; reply was: {str(msg.get('content'))[:200]!r}"
    fn = calls[0]["function"]
    try:
        args = json.loads(fn["arguments"])
    except json.JSONDecodeError:
        return False, f"arguments are not valid JSON: {fn['arguments'][:200]!r}"
    ok = fn["name"] == "create_document" and len(args.get("headings", [])) == 3
    return ok, f"{fn['name']}({json.dumps(args)})"


def png_solid(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    raw = b"".join(b"\x00" + bytes(rgb) * width for _ in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def check_vision(base: str, model: str) -> tuple[bool, str]:
    img = base64.b64encode(png_solid(256, 256, (220, 20, 20))).decode()
    try:
        res = post(f"{base}/v1/chat/completions", {
            "model": model, "temperature": 0, "max_tokens": 1024,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": "What single colour fills this image? Answer with one word."},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img}"}},
            ]}],
        })
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}: {e.read().decode()[:200]} (is --mmproj loaded?)"
    text = (res["choices"][0]["message"].get("content") or "").strip()
    return "red" in text.lower(), repr(text[:100])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="http://127.0.0.1:8080")
    ap.add_argument("--sizes", default="512,4000,16000", help="prompt sizes in tokens")
    ap.add_argument("--gen", type=int, default=256, help="tokens to generate per run")
    ap.add_argument("--json", help="write results to this file")
    args = ap.parse_args()
    base = args.url.rstrip("/")

    try:
        get(f"{base}/health")
    except Exception as e:  # noqa: BLE001
        print(f"Server not healthy at {base}/health: {e}", file=sys.stderr)
        return 1
    props = get(f"{base}/props")
    model = get(f"{base}/v1/models")["data"][0]["id"]
    n_ctx = props.get("default_generation_settings", {}).get("n_ctx") or props.get("n_ctx")
    print(f"Model: {model}   context per slot: {n_ctx}   modalities: {props.get('modalities')}")
    print("VRAM idle:", ", ".join(f"GPU{g['gpu']} {g['used_mib']}/{g['total_mib']} MiB" for g in vram()) or "n/a")

    results: dict[str, Any] = {"model": model, "n_ctx": n_ctx, "runs": [], "checks": {}}
    print(f"\n{'prompt':>8} {'pp tok/s':>9} {'gen tok/s':>10} {'TTFT s':>7}  VRAM MiB per GPU")
    for size in (int(s) for s in args.sizes.split(",")):
        if n_ctx and size + args.gen > n_ctx:
            print(f"{size:>8}  skipped (exceeds context {n_ctx})")
            continue
        r = bench_size(base, model, size, args.gen)
        results["runs"].append(r)
        mem = " ".join(f"{g['used_mib']}" for g in r["vram"]) or "n/a"
        print(f"{r['prompt_tokens']:>8} {r['prompt_tok_s']:>9} {r['gen_tok_s']:>10} {r['ttft_s']:>7}  {mem}")

    print()
    failed = 0
    for name, fn in (("tool calling", check_tool_call), ("image input", check_vision)):
        try:
            ok, detail = fn(base, model)
        except Exception as e:  # noqa: BLE001
            ok, detail = False, f"error: {e}"
        failed += not ok
        results["checks"][name] = {"ok": ok, "detail": detail}
        print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}")

    if args.json:
        with open(args.json, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nWrote {args.json}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
