"""Generated-file store and signed download links.

Layout:  <data>/files/<file_id>/<filename>  plus  <data>/files/<file_id>/meta.json
Download links are HMAC-signed and expire, so they can be pasted into chat and
opened in a browser without the tool-server API key.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import mimetypes
import re
import secrets
import shutil
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .errors import ToolError, not_found

GEN_PREFIX = "gen_"
_ID_RE = re.compile(r"^gen_[0-9a-f]{16}$")
_UNSAFE = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


@dataclass
class StoredFile:
    file_id: str
    filename: str
    path: Path
    mime: str
    created: float
    user: str | None = None
    kind: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def meta(self) -> dict[str, Any]:
        d = asdict(self)
        d["path"] = self.path.name
        return d


def safe_filename(name: str, default_ext: str = "") -> str:
    name = _UNSAFE.sub(" ", name).strip(" .") or "file"
    name = re.sub(r"\s+", " ", name)[:120]
    if default_ext and not name.lower().endswith(default_ext):
        name += default_ext
    return name


class FileStore:
    def __init__(self, root: Path, signing_key: str, public_url: str, ttl_hours: int) -> None:
        self.root = root
        self.key = signing_key.encode()
        self.public_url = public_url.rstrip("/")
        self.ttl_s = ttl_hours * 3600

    # ---------------------------------------------------------------- write
    def new_id(self) -> str:
        return GEN_PREFIX + secrets.token_hex(8)

    def save_bytes(
        self,
        data: bytes,
        filename: str,
        *,
        user: str | None,
        kind: str,
        file_id: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> StoredFile:
        file_id = file_id or self.new_id()
        folder = self._folder(file_id)
        if folder.exists():  # new version of an existing file: replace it
            for p in folder.iterdir():
                p.unlink()
        folder.mkdir(parents=True, exist_ok=True)
        filename = safe_filename(filename)
        path = folder / filename
        path.write_bytes(data)
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        sf = StoredFile(file_id, filename, path, mime, time.time(), user, kind, extra or {})
        (folder / "meta.json").write_text(json.dumps(sf.meta(), indent=2, default=str))
        return sf

    def save_file(self, src: Path, filename: str, **kw: Any) -> StoredFile:
        return self.save_bytes(src.read_bytes(), filename, **kw)

    # ---------------------------------------------------------------- read
    def get(self, file_id: str) -> StoredFile:
        if not _ID_RE.match(file_id):
            raise not_found(f"Generated file '{file_id}'")
        meta_path = self._folder(file_id) / "meta.json"
        if not meta_path.exists():
            raise not_found(f"Generated file '{file_id}'", "Check the file_id returned by the tool that made it.")
        m = json.loads(meta_path.read_text())
        return StoredFile(
            m["file_id"],
            m["filename"],
            self._folder(file_id) / m["path"],
            m["mime"],
            m["created"],
            m.get("user"),
            m.get("kind", ""),
            m.get("extra", {}),
        )

    def delete(self, file_id: str) -> None:
        shutil.rmtree(self._folder(file_id), ignore_errors=True)

    # ---------------------------------------------------------------- links
    def _sig(self, file_id: str, filename: str, exp: int) -> str:
        msg = f"{file_id}\n{filename}\n{exp}".encode()
        return hmac.new(self.key, msg, hashlib.sha256).hexdigest()[:32]

    def download_url(self, sf: StoredFile) -> str:
        exp = int(time.time()) + self.ttl_s
        sig = self._sig(sf.file_id, sf.filename, exp)
        return f"{self.public_url}/files/{sf.file_id}/{quote(sf.filename)}?exp={exp}&sig={sig}"

    def verify(self, file_id: str, filename: str, exp: int, sig: str) -> StoredFile:
        if exp < time.time():
            raise ToolError(
                "link_expired", "This download link has expired.", "Ask the assistant to share the file again."
            )
        if not hmac.compare_digest(self._sig(file_id, filename, exp), sig):
            raise ToolError("bad_signature", "Invalid download link.")
        sf = self.get(file_id)
        if sf.filename != filename:
            raise not_found("File")
        return sf

    def _folder(self, file_id: str) -> Path:
        return self.root / file_id
