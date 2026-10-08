"""JSON spec for create_document. Kept flat and explicit so a ~30B model fills it reliably."""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

HEX = re.compile(r"^#?[0-9A-Fa-f]{6}$")
Cell = str | int | float | None


class _Block(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HeadingBlock(_Block):
    type: Literal["heading"]
    text: str = Field(min_length=1)
    level: int = Field(1, ge=1, le=3, description="1 = chapter, 2 = section, 3 = sub-section")


class ParagraphBlock(_Block):
    type: Literal["paragraph"]
    text: str = Field(description="Supports **bold**, *italic*, `code` and [link](https://...)")
    align: Literal["left", "center", "right", "justify"] = "left"


class ListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    level: int = Field(0, ge=0, le=2, description="0 = top level, 1-2 = nested")


class ListBlock(_Block):
    type: Literal["list"]
    style: Literal["bullet", "number"] = "bullet"
    items: list[str | ListItem] = Field(min_length=1)


class TableBlock(_Block):
    type: Literal["table"]
    columns: list[str] = Field(min_length=1, description="Header row")
    rows: list[list[Cell]] = Field(default_factory=list, description="Each row has one value per column")
    caption: str | None = None
    column_widths_cm: list[float] | None = None

    @model_validator(mode="after")
    def _check_rows(self) -> TableBlock:
        n = len(self.columns)
        for i, row in enumerate(self.rows):
            if len(row) > n:
                raise ValueError(f"table row {i} has {len(row)} values but there are {n} columns")
        self.rows = [list(r) + [None] * (n - len(r)) for r in self.rows]
        if self.column_widths_cm is not None and len(self.column_widths_cm) != n:
            raise ValueError(f"column_widths_cm needs {n} values, one per column")
        return self


class ImageBlock(_Block):
    type: Literal["image"]
    file_id: str = Field(description="file_id of an uploaded or generated image (PNG/JPG)")
    width_cm: float = Field(15, gt=1, le=25)
    caption: str | None = None


class QuoteBlock(_Block):
    type: Literal["quote"]
    text: str
    attribution: str | None = None


class CalloutBlock(_Block):
    type: Literal["callout"]
    text: str
    title: str | None = None
    tone: Literal["info", "note", "warning", "success"] = "info"


class PageBreakBlock(_Block):
    type: Literal["page_break"]


class MarkdownBlock(_Block):
    type: Literal["markdown"]
    text: str = Field(description="Markdown: # headings, paragraphs, - bullets, 1. numbers, | tables |, > quotes")


Block = Annotated[
    HeadingBlock
    | ParagraphBlock
    | ListBlock
    | TableBlock
    | ImageBlock
    | QuoteBlock
    | CalloutBlock
    | PageBreakBlock
    | MarkdownBlock,
    Field(discriminator="type"),
]


class DocStyle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body_font: str = "Calibri"
    heading_font: str = "Calibri"
    body_size_pt: float = Field(11, ge=8, le=16)
    accent_color: str = Field("1F4E79", description="Hex colour for headings and table headers")
    text_color: str = "222222"

    @field_validator("accent_color", "text_color")
    @classmethod
    def _hex(cls, v: str) -> str:
        if not HEX.match(v):
            raise ValueError("colour must be 6 hex digits, e.g. 1F4E79")
        return v.lstrip("#").upper()


class DocumentSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1)
    subtitle: str | None = None
    author: str | None = None
    date: str | None = Field(None, description="Shown on the cover, e.g. 'October 2026'")
    filename: str | None = Field(None, description="Without extension; defaults to the title")
    cover_page: bool = Field(False, description="Separate cover page with title, subtitle, author, date")
    logo_file_id: str | None = Field(None, description="Image shown on the cover page")
    toc: bool = Field(False, description="Table of contents after the cover")
    header_text: str | None = None
    footer_text: str | None = None
    page_numbers: bool = True
    page_size: Literal["A4", "Letter"] = "A4"
    orientation: Literal["portrait", "landscape"] = "portrait"
    style: DocStyle = Field(default_factory=DocStyle)
    blocks: list[Block] = Field(default_factory=list)
