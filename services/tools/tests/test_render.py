from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import pytest

from app.generators.doc_spec import DocumentSpec
from app.generators.docx_builder import build_docx
from app.render import render_pages

pytestmark = [
    pytest.mark.libreoffice,
    pytest.mark.skipif(
        not (shutil.which("soffice") and shutil.which("pdftoppm")), reason="LibreOffice/poppler not installed"
    ),
]


def test_docx_renders_to_pages(tmp_path: Path) -> None:
    spec = DocumentSpec.model_validate(
        {
            "title": "Render",
            "cover_page": True,
            "toc": True,
            "blocks": [{"type": "heading", "text": "One", "level": 1}, {"type": "paragraph", "text": "Body"}],
        }
    )
    src = tmp_path / "r.docx"
    src.write_bytes(build_docx(spec).data)
    pages = asyncio.run(render_pages(src, tmp_path / "out", dpi=40))
    assert len(pages) == 3  # cover, contents, body
    assert all(p.stat().st_size > 0 for p in pages)
