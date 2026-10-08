"""Convert a Markdown string into document blocks (for the 'markdown' block type)."""

from __future__ import annotations

import re
from typing import Literal

from .doc_spec import (
    Block,
    HeadingBlock,
    ListBlock,
    ListItem,
    PageBreakBlock,
    ParagraphBlock,
    QuoteBlock,
    TableBlock,
)

_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_BULLET = re.compile(r"^(\s*)[-*+]\s+(.*)$")
_NUMBER = re.compile(r"^(\s*)\d+[.)]\s+(.*)$")
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


def _cells(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def _level(indent: str) -> int:
    return min(2, len(indent.replace("\t", "  ")) // 2)


def markdown_to_blocks(text: str) -> list[Block]:
    lines = text.replace("\r\n", "\n").split("\n")
    blocks: list[Block] = []
    para: list[str] = []
    i = 0

    def flush() -> None:
        if para:
            blocks.append(ParagraphBlock(type="paragraph", text=" ".join(s.strip() for s in para)))
            para.clear()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            flush()
            i += 1
            continue
        if stripped in ("---", "***", "<!-- pagebreak -->", "\\pagebreak"):
            flush()
            if stripped != "---":
                blocks.append(PageBreakBlock(type="page_break"))
            i += 1
            continue
        if m := _HEADING.match(stripped):
            flush()
            blocks.append(HeadingBlock(type="heading", text=m.group(2), level=min(3, len(m.group(1)))))
            i += 1
            continue
        if stripped.startswith("|") and i + 1 < len(lines) and _TABLE_SEP.match(lines[i + 1]):
            flush()
            cols = _cells(stripped)
            rows: list[list[str | int | float | None]] = []
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(list(_cells(lines[i])[: len(cols)]))
                i += 1
            blocks.append(TableBlock(type="table", columns=cols, rows=rows))
            continue
        if stripped.startswith(">"):
            flush()
            quote = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip().lstrip(">").strip())
                i += 1
            blocks.append(QuoteBlock(type="quote", text=" ".join(quote)))
            continue
        bullet, number = _BULLET.match(line), _NUMBER.match(line)
        if bullet or number:
            flush()
            style: Literal["bullet", "number"] = "bullet" if bullet else "number"
            pattern = _BULLET if bullet else _NUMBER
            items: list[str | ListItem] = []
            while i < len(lines) and (m := pattern.match(lines[i])):
                items.append(ListItem(text=m.group(2), level=_level(m.group(1))))
                i += 1
            blocks.append(ListBlock(type="list", style=style, items=items))
            continue
        para.append(stripped)
        i += 1
    flush()
    return blocks
