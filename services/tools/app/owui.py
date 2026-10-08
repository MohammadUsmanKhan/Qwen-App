"""Read-only access to files users uploaded through Open WebUI.

Open WebUI does not pass uploaded files to OpenAPI tool servers, so the tool
server mounts Open WebUI's data directory read-only and looks uploads up in its
SQLite database (table ``file``). The calling user is identified by the
``X-OpenWebUI-User-Id`` header (needs ENABLE_FORWARD_USER_INFO_HEADERS=true).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .errors import ToolError, not_found


@dataclass
class Upload:
    file_id: str
    filename: str
    path: Path
    user_id: str
    created_at: int
    size: int | None
    content_type: str | None


class OpenWebUIFiles:
    def __init__(self, data_dir: Path, container_data_dir: str) -> None:
        self.data_dir = data_dir
        self.container_data_dir = container_data_dir.rstrip("/")

    @property
    def db_path(self) -> Path:
        return self.data_dir / "webui.db"

    def available(self) -> bool:
        return self.db_path.exists()

    def _connect(self) -> sqlite3.Connection:
        if not self.available():
            raise ToolError(
                "uploads_unavailable",
                "Uploaded files are not reachable from the tool server.",
                "Tell the user the tool server cannot see Open WebUI uploads (check the volume mount).",
            )
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, timeout=5)
        conn.row_factory = sqlite3.Row
        return conn

    def _row_to_upload(self, row: sqlite3.Row) -> Upload:
        meta = {}
        if row["meta"]:
            try:
                meta = json.loads(row["meta"])
            except (TypeError, json.JSONDecodeError):
                meta = {}
        return Upload(
            file_id=row["id"],
            filename=row["filename"],
            path=self._map_path(row["path"] or ""),
            user_id=row["user_id"],
            created_at=int(row["created_at"] or 0),
            size=meta.get("size"),
            content_type=meta.get("content_type"),
        )

    def _map_path(self, stored: str) -> Path:
        if stored.startswith(("s3://", "gs://", "az://", "http")):
            raise ToolError(
                "unsupported_storage",
                f"Upload is in cloud storage ({stored.split(':')[0]}).",
                "Only Open WebUI's local storage provider is supported.",
            )
        if stored.startswith(self.container_data_dir):
            return self.data_dir / stored[len(self.container_data_dir) :].lstrip("/")
        return self.data_dir / "uploads" / Path(stored).name

    def list(self, user_id: str | None, limit: int = 20) -> list[Upload]:
        with self._connect() as conn:
            if user_id:
                rows = conn.execute(
                    "SELECT id, user_id, filename, path, meta, created_at FROM file "
                    "WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                    (user_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, user_id, filename, path, meta, created_at FROM file ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [self._row_to_upload(r) for r in rows]

    def get(self, file_id: str, user_id: str | None, is_admin: bool = False) -> Upload:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, user_id, filename, path, meta, created_at FROM file WHERE id = ?", (file_id,)
            ).fetchone()
        if row is None:
            raise not_found(f"File '{file_id}'", "Call list_uploaded_files to see the user's files and their ids.")
        up = self._row_to_upload(row)
        if user_id and up.user_id != user_id and not is_admin:
            raise not_found(f"File '{file_id}'", "Call list_uploaded_files to see the user's files and their ids.")
        if not up.path.exists():
            raise ToolError(
                "file_missing",
                f"'{up.filename}' is registered but its data is missing on disk.",
                "Ask the user to upload the file again.",
            )
        return up
