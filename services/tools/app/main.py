"""OpenAPI tool server registered in Open WebUI.

Each tool is a POST /tools/<name> endpoint whose operationId is the tool name the
model sees. Tools always answer HTTP 200 with ``{"ok": true, ...}`` or
``{"ok": false, "error": {...}}`` (see errors.py).
"""

from __future__ import annotations

import functools
import hashlib
import json
import logging
import os
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from . import readers
from .calllog import CallLog
from .config import Settings, get_settings
from .errors import ToolError
from .generators.doc_spec import Block, DocumentSpec
from .generators.docx_builder import BuildResult, build_docx
from .openapi_inline import inline_refs
from .owui import OpenWebUIFiles
from .storage import GEN_PREFIX, FileStore, StoredFile, safe_filename

log = logging.getLogger("tools")
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff"}
USER_ID_HEADER = "x-openwebui-user-id"
USER_ROLE_HEADER = "x-openwebui-user-role"


# ---------------------------------------------------------------------- context
class Context:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store = FileStore(settings.files_dir, settings.signing_key, settings.public_url, settings.link_ttl_hours)
        self.uploads = OpenWebUIFiles(settings.owui_data_dir, settings.owui_container_data_dir)
        self.calls = CallLog(settings.logs_dir)
        self.cache_dir = settings.data_dir / "cache"


@functools.lru_cache
def get_ctx() -> Context:
    return Context(get_settings())


class Caller(BaseModel):
    user_id: str | None
    is_admin: bool


def caller(request: Request) -> Caller:
    return Caller(
        user_id=request.headers.get(USER_ID_HEADER), is_admin=request.headers.get(USER_ROLE_HEADER) == "admin"
    )


bearer = HTTPBearer(auto_error=False)


def require_key(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> None:
    key = get_ctx().settings.api_key
    if key and (creds is None or creds.credentials != key):
        raise HTTPException(status_code=401, detail="invalid or missing API key")


# ---------------------------------------------------------------------- app
app = FastAPI(
    title="Workspace tools",
    version="0.1.0",
    description="Read uploaded files and create Word documents. Every tool returns ok=true or an error "
    "with a hint saying how to fix the call.",
)


def custom_openapi() -> dict[str, Any]:
    if app.openapi_schema is None:
        from fastapi.openapi.utils import get_openapi

        schema = get_openapi(title=app.title, version=app.version, description=app.description, routes=app.routes)
        app.openapi_schema = inline_refs(schema)
    return app.openapi_schema


app.openapi = custom_openapi  # type: ignore[method-assign]


@app.exception_handler(RequestValidationError)
async def _invalid_args(request: Request, exc: RequestValidationError) -> JSONResponse:
    problems = "; ".join(f"{'.'.join(str(x) for x in e['loc'][1:])}: {e['msg']}" for e in exc.errors()[:8])
    err = ToolError(
        "invalid_arguments",
        f"The arguments don't match the tool schema: {problems}",
        "Fix the listed fields and call the tool again.",
    )
    tool = request.url.path.rsplit("/", 1)[-1]
    get_ctx().calls.write(
        tool, request.headers.get(USER_ID_HEADER), {"raw": "unparsed"}, time.perf_counter(), err.to_dict()
    )
    return JSONResponse(err.to_dict(), status_code=200)


ToolFn = Callable[..., Awaitable[dict[str, Any]]]


def logged(name: str) -> Callable[[ToolFn], ToolFn]:
    """Log every call and turn exceptions into structured tool errors."""

    def deco(fn: ToolFn) -> ToolFn:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
            started = time.perf_counter()
            body = next((v for v in kwargs.values() if isinstance(v, BaseModel) and not isinstance(v, Caller)), None)
            who = next((v for v in kwargs.values() if isinstance(v, Caller)), None)
            try:
                result = {"ok": True, **await fn(*args, **kwargs)}
            except ToolError as e:
                result = e.to_dict()
            except ValidationError as e:
                result = ToolError("invalid_arguments", str(e)[:800], "Fix the fields and try again.").to_dict()
            except Exception as e:  # noqa: BLE001
                log.exception("tool %s crashed", name)
                result = ToolError(
                    "internal_error",
                    f"{type(e).__name__}: {e}",
                    "This is a tool bug; tell the user what you were trying to do.",
                ).to_dict()
            get_ctx().calls.write(
                name, who.user_id if who else None, body.model_dump(mode="json") if body else None, started, result
            )
            return jsonable_encoder(result)

        return wrapper

    return deco


# ---------------------------------------------------------------------- helpers
def _require_user(who: Caller) -> None:
    if get_ctx().settings.require_user_header and not who.user_id:
        raise ToolError(
            "user_unknown",
            "The tool server did not receive the user's identity.",
            "Admin: enable ENABLE_FORWARD_USER_INFO_HEADERS in Open WebUI.",
        )


def _open_input(file_id: str, who: Caller) -> tuple[Path, str]:
    """Resolve a file_id (generated 'gen_…' or an Open WebUI upload id) to a local path + filename."""
    ctx = get_ctx()
    file_id = file_id.strip()
    if file_id.startswith(GEN_PREFIX):
        sf = ctx.store.get(file_id)
        if sf.user and who.user_id and sf.user != who.user_id and not who.is_admin:
            raise ToolError("not_found", f"Generated file '{file_id}' was not found.")
        return sf.path, sf.filename
    _require_user(who)
    up = ctx.uploads.get(file_id, who.user_id, who.is_admin)
    return up.path, up.filename


def _image_resolver(who: Caller) -> Callable[[str], Path]:
    def resolve(file_id: str) -> Path:
        path, name = _open_input(file_id, who)
        if Path(name).suffix.lower() not in IMAGE_EXT:
            raise ToolError("not_an_image", f"'{name}' is not an image.")
        return path

    return resolve


def _file_result(sf: StoredFile, extra: dict[str, Any]) -> dict[str, Any]:
    url = get_ctx().store.download_url(sf)
    return {
        "file_id": sf.file_id,
        "filename": sf.filename,
        "download_url": url,
        "markdown_link": f"[{sf.filename}]({url})",
        **extra,
        "next_step": "Give the user markdown_link and a one-line summary.",
    }


def _doc_summary(res: BuildResult) -> dict[str, Any]:
    return {
        "summary": {
            "sections": [f"{'  ' * (lvl - 1)}{text}" for lvl, text in res.headings][:40],
            "tables": res.tables,
            "images": res.images,
            "words": res.words,
        },
        "warnings": res.warnings,
    }


# ---------------------------------------------------------------------- routes: infra
@app.get("/health", include_in_schema=False)
async def health() -> dict[str, Any]:
    ctx = get_ctx()
    return {"status": "ok", "uploads_visible": ctx.uploads.available()}


@app.get("/files/{file_id}/{filename}", include_in_schema=False)
async def download(file_id: str, filename: str, exp: int, sig: str) -> FileResponse:
    try:
        sf = get_ctx().store.verify(file_id, filename, exp, sig)
    except ToolError as e:
        raise HTTPException(status_code=403 if e.code != "not_found" else 404, detail=e.message) from e
    return FileResponse(sf.path, media_type=sf.mime, filename=sf.filename)


# ---------------------------------------------------------------------- tools: files
class ListUploadsArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    limit: int = Field(20, ge=1, le=100, description="How many recent files to list")


@app.post(
    "/tools/list_uploaded_files",
    operation_id="list_uploaded_files",
    summary="List files the user uploaded, newest first, with their file_id.",
    description="Call this first when the user refers to a file they uploaded, to get its file_id.",
    dependencies=[Depends(require_key)],
)
@logged("list_uploaded_files")
async def list_uploaded_files(args: ListUploadsArgs, who: Caller = Depends(caller)) -> dict[str, Any]:
    _require_user(who)
    files = get_ctx().uploads.list(who.user_id, args.limit)
    return {
        "files": [
            {
                "file_id": f.file_id,
                "filename": f.filename,
                "size_bytes": f.size,
                "uploaded": time.strftime("%Y-%m-%d %H:%M", time.gmtime(f.created_at)),
            }
            for f in files
        ]
    }


class ReadFileArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    file_id: str = Field(description="file_id from list_uploaded_files or from a tool that created a file")
    offset: int = Field(0, ge=0, description="Character offset to continue reading from (use next_offset)")
    max_chars: int | None = Field(None, ge=1000, le=60000, description="Characters to return (default 20000)")
    sheet: str | None = Field(None, description="Spreadsheets only: one sheet name")
    force_ocr: bool = Field(False, description="OCR every page, for scans whose text layer is wrong")


@app.post(
    "/tools/read_file",
    operation_id="read_file",
    summary="Read a file and return its content as Markdown.",
    description="Works for PDF, Word, PowerPoint, Excel, CSV, HTML, text and images (OCR). Long files "
    "are returned in parts: call again with offset=next_offset to continue.",
    dependencies=[Depends(require_key)],
)
@logged("read_file")
async def read_file(args: ReadFileArgs, who: Caller = Depends(caller)) -> dict[str, Any]:
    ctx = get_ctx()
    path, filename = _open_input(args.file_id, who)
    key = hashlib.sha256(f"{args.file_id}|{path.stat().st_mtime_ns}|{args.sheet}|{args.force_ocr}".encode())
    cache = ctx.cache_dir / f"{key.hexdigest()[:24]}.json"
    if cache.exists():
        cached = json.loads(cache.read_text())
        ex = readers.Extracted(cached["kind"], cached["markdown"], cached["method"], cached["notes"])
    else:
        ex = await readers.extract(
            path,
            filename,
            docling_url=ctx.settings.docling_url,
            docling_timeout=ctx.settings.docling_timeout_s,
            sheet=args.sheet,
            force_ocr=args.force_ocr,
        )
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(ex.__dict__))
    limit = args.max_chars or ctx.settings.read_max_chars
    text = ex.markdown
    chunk = text[args.offset : args.offset + limit]
    end = args.offset + len(chunk)
    notes = list(ex.notes)
    if end < len(text):
        notes.append(
            f"Showing characters {args.offset}-{end} of {len(text)}. For specific questions the "
            "chat's document search may be faster than reading everything."
        )
    return {
        "file_id": args.file_id,
        "filename": filename,
        "type": ex.kind,
        "method": ex.method,
        "chars_total": len(text),
        "offset": args.offset,
        "next_offset": end if end < len(text) else None,
        "content": chunk,
        "notes": notes,
    }


# ---------------------------------------------------------------------- tools: Word
@app.post(
    "/tools/create_document",
    operation_id="create_document",
    summary="Create a Word (.docx) document from a structured spec.",
    description="Give the title and a list of blocks (heading, paragraph, list, table, image, quote, "
    "callout, page_break, markdown). Layout and styling are automatic. For long documents "
    "create it with the first sections, then add the rest with append_document_section.",
    dependencies=[Depends(require_key)],
)
@logged("create_document")
async def create_document(spec: DocumentSpec, who: Caller = Depends(caller)) -> dict[str, Any]:
    res = build_docx(spec, _image_resolver(who))
    name = safe_filename(spec.filename or spec.title, ".docx")
    sf = get_ctx().store.save_bytes(
        res.data, name, user=who.user_id, kind="docx", extra={"spec": spec.model_dump(mode="json")}
    )
    return _file_result(sf, _doc_summary(res))


class AppendSectionArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file_id: str = Field(description="file_id returned by create_document")
    blocks: list[Block] = Field(min_length=1, description="Blocks to add at the end, same format as create_document")


@app.post(
    "/tools/append_document_section",
    operation_id="append_document_section",
    summary="Add more blocks to the end of a document made with create_document.",
    description="Use to build long documents section by section. Returns an updated download link.",
    dependencies=[Depends(require_key)],
)
@logged("append_document_section")
async def append_document_section(args: AppendSectionArgs, who: Caller = Depends(caller)) -> dict[str, Any]:
    store = get_ctx().store
    sf = store.get(args.file_id)
    if sf.kind != "docx" or "spec" not in sf.extra:
        raise ToolError(
            "wrong_file",
            f"'{args.file_id}' was not made by create_document.",
            "Pass the file_id that create_document returned.",
        )
    if sf.user and who.user_id and sf.user != who.user_id and not who.is_admin:
        raise ToolError("not_found", f"Generated file '{args.file_id}' was not found.")
    spec = DocumentSpec.model_validate(sf.extra["spec"])
    spec.blocks.extend(args.blocks)
    res = build_docx(spec, _image_resolver(who))
    sf = store.save_bytes(
        res.data,
        sf.filename,
        user=sf.user,
        kind="docx",
        file_id=sf.file_id,
        extra={"spec": spec.model_dump(mode="json")},
    )
    return _file_result(sf, _doc_summary(res))


logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
