"""One JSON line per tool call: tool, user, arguments, duration, outcome.

Written to <data>/logs/tool_calls.jsonl for debugging how the model uses tools.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

log = logging.getLogger("tools.calls")
_lock = threading.Lock()
MAX_ARG_CHARS = 4000


class CallLog:
    def __init__(self, logs_dir: Path) -> None:
        self.path = logs_dir / "tool_calls.jsonl"

    def write(self, tool: str, user: str | None, args: Any, started: float, result: dict[str, Any]) -> None:
        err = result.get("error") if isinstance(result, dict) else None
        entry = {
            "ts": datetime.now(UTC).isoformat(timespec="seconds"),
            "tool": tool,
            "user": user,
            "duration_ms": round((time.perf_counter() - started) * 1000),
            "ok": bool(result.get("ok", True)) if isinstance(result, dict) else True,
            "error_code": err.get("code") if err else None,
            "args": _truncate(args),
        }
        log.info(
            "%s ok=%s %dms%s", tool, entry["ok"], entry["duration_ms"], f" error={entry['error_code']}" if err else ""
        )
        line = json.dumps(entry, default=str)
        with _lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a") as f:
                f.write(line + "\n")


def _truncate(args: Any) -> Any:
    text = json.dumps(args, default=str)
    if len(text) <= MAX_ARG_CHARS:
        return args
    return text[:MAX_ARG_CHARS] + f"...(+{len(text) - MAX_ARG_CHARS} chars)"
