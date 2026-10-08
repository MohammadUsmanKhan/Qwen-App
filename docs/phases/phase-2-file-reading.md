# Phase 2: File reading

**Status: built; the Docling + Open WebUI parts still need testing on the server.**

## What's included
- `docling` service (docling-serve, CPU) with OCR. Open WebUI uses it for all uploads
  (`CONTENT_EXTRACTION_ENGINE=docling`), so uploads are indexed for RAG with OCR for scanned PDFs.
- RAG embeddings: `Qwen/Qwen3-Embedding-0.6B` on CPU inside Open WebUI (downloaded on first start).
- Image understanding: images attached to a chat go straight to the vision model (needs `mmproj` and the
  Vision capability ticked on the model).
- Tool `list_uploaded_files`: the user's recent uploads with their `file_id`.
- Tool `read_file(file_id)`: whole-file Markdown for when RAG snippets aren't enough:
  - PDF, DOCX, PPTX, HTML, images → Docling (OCR on; `force_ocr` for scans with a bad text layer),
    with a basic local fallback if Docling is down.
  - XLSX/XLS/CSV/TSV → pandas: sheet names, row/column counts, column types with min/max/sum,
    first 15 rows, formula count.
  - Long files come back in 20k-character parts (`offset` / `next_offset`); results are cached.

### How the tool server sees uploads
Open WebUI doesn't pass uploaded files to OpenAPI tool servers. The tool server therefore mounts
`./data/open-webui` read-only and looks files up in Open WebUI's `webui.db`. Users are told apart by the
`X-OpenWebUI-User-Id` header (`ENABLE_FORWARD_USER_INFO_HEADERS=true`): users only see their own
uploads; admins can read any. Without the header the tools refuse instead of exposing everyone's files.

## How to test
1. Upload a text PDF, a scanned PDF, a DOCX, a PPTX and an XLSX in one chat with `Qwen Agent`.
2. "What files have I uploaded?" → model calls `list_uploaded_files`.
3. "Summarise the spreadsheet: which sheet has the most rows?" → `read_file` with the sheet summary.
4. "What does page 2 of the scanned PDF say?" → OCR text.
5. Attach a photo and ask about it → answered by the vision model directly.
6. Check `data/tools/logs/tool_calls.jsonl`.

## Known issues
- Relies on Open WebUI's SQLite schema (`file` table: id, user_id, filename, path, meta, created_at) and local
  storage. Postgres or S3 storage would need a small adapter.
- Header-forwarding names are `X-OpenWebUI-User-Id` / `-Role`; if a future Open WebUI renames them, tools
  answer `user_unknown`.
- `DOCLING_PARAMS` format differs between Open WebUI versions; if OCR isn't applied, set the Docling options in
  Admin Settings → Documents.
