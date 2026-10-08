# Phase 3: Tool server + Word documents

**Status: built and unit-tested here (31 tests passing); Open WebUI integration still needs testing on the server.**

## What's included
- FastAPI tool server (`services/tools`) registered in Open WebUI as an OpenAPI tool server.
  - The OpenAPI schema has `$ref`s inlined and titles stripped, so any client can read it and it costs fewer tokens.
  - Every tool answers HTTP 200 with `ok: true` or `ok: false` + `error {code, message, hint}`, so the model
    always sees what went wrong and how to fix it. Schema mismatches come back as `invalid_arguments` listing the bad fields.
  - Each call is logged to `data/tools/logs/tool_calls.jsonl` (tool, user, arguments, duration, result).
  - Bearer-key auth between Open WebUI and the tool server.
- `create_document(spec)`: the model sends a JSON spec, and the code does all layout:
  - cover page (title, subtitle, author, date, logo), table of contents, header text, footer text with "Page X of Y"
  - blocks: heading (1–3), paragraph with **bold** / *italic* / `code` / links, bullet and numbered lists
    (nested; each numbered list restarts at 1), tables (shaded header row repeated on each page, banded rows,
    right-aligned numbers, automatic column widths), images with captions, quotes, callouts, page breaks,
    and a `markdown` block for small models that write Markdown more reliably than JSON
  - style: body/heading fonts, size, accent colour (brand profiles will plug in here in Phase 6)
  - A4/Letter, portrait/landscape
- `append_document_section(file_id, blocks)`: builds long documents section by section; the contents page
  is regenerated each time.
- Downloads: files are stored in `data/tools/files/`; links are HMAC-signed and expire after
  `TOOLS_LINK_TTL_HOURS`. The tool returns `markdown_link` for the model to paste into chat.
- LibreOffice + poppler in the image (`app/render.py`) for page previews; Phase 6 visual checks will use them.
- System prompt for the agent: `config/prompts/system.md`.

## How to test
```bash
make test                       # unit tests
```
In chat with `Qwen Agent`:
1. "Write a one-page memo announcing the new parking policy." → a link appears; the .docx opens in Word.
2. "Write a 10-section technical proposal for a solar installation." → it outlines first, then calls
   `create_document` once and `append_document_section` for the rest.
3. Upload a CSV and say "make a Word report with a table of the top 10 rows and a short analysis".

## Known issues
- Contents page: entries are shown immediately; page numbers fill in when Word asks to "update fields"
  on opening (LibreOffice previews show entries without numbers).
- No charts yet (Phase 5 adds `render_chart`/`render_diagram`, whose PNGs plug into `image` blocks).
- Tool server runs as root inside its container; hardening is Phase 9.
- Jobs and timeouts for long tasks come with the first slow tools (images, deep research).
