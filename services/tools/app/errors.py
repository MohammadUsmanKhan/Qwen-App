"""Structured tool errors.

Every tool failure is returned as HTTP 200 with
``{"ok": false, "error": {"code", "message", "hint"}}`` so the model always sees
the error (some clients hide non-2xx bodies) and the hint tells it what to do next.
"""

from __future__ import annotations

from typing import Any


class ToolError(Exception):
    def __init__(self, code: str, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint

    def to_dict(self) -> dict[str, Any]:
        return {"ok": False, "error": {"code": self.code, "message": self.message, "hint": self.hint}}


def not_found(what: str, hint: str = "") -> ToolError:
    return ToolError("not_found", f"{what} was not found.", hint)
