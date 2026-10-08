"""Client for docling-serve: PDF/DOCX/PPTX/HTML/images → Markdown, with OCR."""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

from ..errors import ToolError

log = logging.getLogger(__name__)

ENDPOINTS = ("/v1/convert/file", "/v1alpha/convert/file")


async def convert(
    base_url: str, path: Path, filename: str, *, ocr: bool = True, force_ocr: bool = False, timeout: float = 600
) -> str:
    form = {
        "to_formats": "md",
        "do_ocr": str(ocr).lower(),
        "force_ocr": str(force_ocr).lower(),
        "image_export_mode": "placeholder",
        "table_mode": "accurate",
    }
    async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
        last_error = ""
        for endpoint in ENDPOINTS:
            with path.open("rb") as f:
                resp = await client.post(endpoint, data=form, files={"files": (filename, f)})
            if resp.status_code == 404:
                last_error = f"{endpoint} not found"
                continue
            if resp.status_code >= 400:
                raise ToolError("extraction_failed", f"Docling returned HTTP {resp.status_code}: {resp.text[:300]}")
            body = resp.json()
            doc = body.get("document") or {}
            md = doc.get("md_content")
            if md is None:
                errs = body.get("errors") or body.get("status")
                raise ToolError("extraction_failed", f"Docling produced no text ({errs}).")
            return str(md)
    raise ToolError("extraction_failed", f"Docling API not found at {base_url} ({last_error}).")
