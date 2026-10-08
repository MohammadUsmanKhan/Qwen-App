"""Make the OpenAPI schema easy for clients and small models.

FastAPI emits request bodies as ``$ref`` into ``components/schemas``. Some tool
clients don't resolve references, and every model sees the schema as tokens, so
references are inlined into each operation and noise keys (``title``) dropped.
"""

from __future__ import annotations

import copy
from typing import Any

DROP_KEYS = {"title"}


def _resolve(node: Any, components: dict[str, Any], seen: tuple[str, ...] = ()) -> Any:
    if isinstance(node, list):
        return [_resolve(n, components, seen) for n in node]
    if not isinstance(node, dict):
        return node
    if "$ref" in node:
        name = node["$ref"].rsplit("/", 1)[-1]
        if name in seen:  # recursive schema: leave the reference in place
            return node
        target = copy.deepcopy(components[name])
        extra = {k: v for k, v in node.items() if k != "$ref"}
        merged = {**_resolve(target, components, (*seen, name)), **_resolve(extra, components, seen)}
        return merged
    out: dict[str, Any] = {}
    for k, v in node.items():
        if k in DROP_KEYS and isinstance(v, str):
            continue
        if k == "discriminator" and isinstance(v, dict):
            out[k] = {"propertyName": v.get("propertyName", "type")}
            continue
        out[k] = _resolve(v, components, seen)
    return out


def inline_refs(schema: dict[str, Any]) -> dict[str, Any]:
    components = schema.get("components", {}).get("schemas", {})
    paths = _resolve(schema.get("paths", {}), components)
    result = {**schema, "paths": paths}
    return result
