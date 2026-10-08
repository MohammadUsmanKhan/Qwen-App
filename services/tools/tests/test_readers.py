from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.errors import ToolError
from app.readers import extract

from .samples import docx_bytes, pptx_bytes, xlsx_bytes

DOWN = "http://127.0.0.1:9"  # nothing listens: forces the local fallback


def run(path: Path, **kw: object):  # type: ignore[no-untyped-def]
    return asyncio.run(extract(path, path.name, docling_url=DOWN, docling_timeout=2, **kw))  # type: ignore[arg-type]


def test_csv(tmp_path: Path) -> None:
    p = tmp_path / "sales.csv"
    p.write_text("region,revenue\nNorth,120\nSouth,80\n")
    ex = run(p)
    assert ex.kind == "table" and ex.method == "pandas"
    assert "Rows: 2, columns: 2" in ex.markdown
    assert "`revenue`: number" in ex.markdown and "sum 200" in ex.markdown
    assert "| North" in ex.markdown


def test_xlsx_sheets_and_formulas(tmp_path: Path) -> None:
    p = tmp_path / "book.xlsx"
    p.write_bytes(xlsx_bytes())
    ex = run(p)
    assert ex.kind == "spreadsheet"
    assert "Sheets: Sales, Notes" in ex.markdown
    assert "formulas: 2" in ex.markdown
    only = run(p, sheet="Notes")
    assert "Sheet: Notes" in only.markdown and "Sheet: Sales" not in only.markdown


def test_docx_fallback_when_docling_down(tmp_path: Path) -> None:
    p = tmp_path / "review.docx"
    p.write_bytes(docx_bytes())
    ex = run(p)
    assert ex.method == "fallback"
    assert "# Quarterly Review" in ex.markdown
    assert "| North | 120 |" in ex.markdown
    assert any("built-in reader" in n for n in ex.notes)


def test_pptx_fallback_includes_notes(tmp_path: Path) -> None:
    p = tmp_path / "deck.pptx"
    p.write_bytes(pptx_bytes())
    ex = run(p)
    assert "## Slide 1" in ex.markdown
    assert "Company A Services" in ex.markdown and "info@company-a.com" in ex.markdown
    assert "Speaker note here" in ex.markdown


def test_text_and_unsupported(tmp_path: Path) -> None:
    t = tmp_path / "notes.md"
    t.write_text("# hi")
    assert run(t).markdown == "# hi"
    bad = tmp_path / "thing.xyz"
    bad.write_bytes(b"\x00")
    with pytest.raises(ToolError) as e:
        run(bad)
    assert e.value.code == "unsupported_type"


def test_image_without_docling_reports_error(tmp_path: Path) -> None:
    p = tmp_path / "scan.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n")
    with pytest.raises(ToolError) as e:
        run(p)
    assert e.value.code == "extraction_failed"


def test_docling_disabled_uses_builtin_reader_immediately(tmp_path: Path) -> None:
    p = tmp_path / "review.docx"
    p.write_bytes(docx_bytes())
    ex = asyncio.run(extract(p, p.name, docling_url="", docling_timeout=2))
    assert ex.method == "fallback" and "# Quarterly Review" in ex.markdown
    img = tmp_path / "photo.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")
    with pytest.raises(ToolError) as e:
        asyncio.run(extract(img, img.name, docling_url="", docling_timeout=2))
    assert "attach it" in e.value.hint
