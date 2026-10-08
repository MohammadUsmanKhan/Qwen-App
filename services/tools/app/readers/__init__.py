"""read_file: detect the file type and return its content as Markdown."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import httpx

from ..errors import ToolError
from . import docling, local, tabular

log = logging.getLogger(__name__)

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".gif"}
DOCLING_EXT = {".pdf", ".docx", ".pptx", ".html", ".htm", ".xhtml"} | IMAGE_EXT
SHEET_EXT = {".xlsx", ".xlsm", ".xls", ".ods"}
DELIMITED_EXT = {".csv": ",", ".tsv": "\t"}
TEXT_EXT = {".txt", ".md", ".markdown", ".json", ".xml", ".yaml", ".yml", ".log", ".py", ".js", ".sql", ".rtf"}
LOCAL_FALLBACK = {
    ".docx": local.read_docx,
    ".pptx": local.read_pptx,
    ".pdf": local.read_pdf,
    ".html": local.read_html,
    ".htm": local.read_html,
    ".xhtml": local.read_html,
}


@dataclass
class Extracted:
    kind: str
    markdown: str
    method: str
    notes: list[str]


async def extract(
    path: Path,
    filename: str,
    *,
    docling_url: str,
    docling_timeout: float,
    sheet: str | None = None,
    force_ocr: bool = False,
) -> Extracted:
    ext = Path(filename).suffix.lower() or path.suffix.lower()
    notes: list[str] = []

    if ext in DELIMITED_EXT:
        return Extracted("table", tabular.read_csv(path, DELIMITED_EXT[ext]), "pandas", notes)
    if ext in SHEET_EXT:
        notes.append("Values shown are the last saved results; use run_python for analysis over all rows.")
        return Extracted("spreadsheet", tabular.read_excel(path, sheet), "pandas", notes)
    if ext in TEXT_EXT:
        return Extracted("text", local.read_text(path), "text", notes)
    if ext in DOCLING_EXT:
        kind = "image" if ext in IMAGE_EXT else ext.lstrip(".")
        if kind == "image":
            notes.append(
                "This is OCR text only. To understand the picture itself, the user should attach "
                "the image to the chat message so you can see it directly."
            )
        try:
            md = await docling.convert(
                docling_url, path, filename, ocr=True, force_ocr=force_ocr, timeout=docling_timeout
            )
            return Extracted(kind, md, "docling", notes)
        except (httpx.HTTPError, ToolError) as e:
            fallback = LOCAL_FALLBACK.get(ext)
            if fallback is None:
                raise ToolError(
                    "extraction_failed",
                    f"Could not extract text from {filename}: {e}",
                    "The document service may be down; try again shortly.",
                ) from e
            log.warning("docling failed for %s (%s); using local fallback", filename, e)
            md = fallback(path)
            notes.append("Extracted with the basic fallback reader (no OCR, simplified layout).")
            if ext == ".pdf" and len(md.strip()) < 50 * max(1, md.count("## Page")):
                notes.append("Very little text found — this may be a scanned PDF that needs OCR.")
            return Extracted(kind, md, "fallback", notes)
    raise ToolError(
        "unsupported_type",
        f"Files of type '{ext or 'unknown'}' can't be read.",
        "Supported: PDF, DOCX, PPTX, XLSX/XLS, CSV/TSV, HTML, TXT/MD/JSON, and images (OCR).",
    )
