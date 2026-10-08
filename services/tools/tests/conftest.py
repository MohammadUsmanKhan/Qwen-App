from __future__ import annotations

import sqlite3
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

API_KEY = "test-key"
ALICE = "user-alice"
BOB = "user-bob"


def make_owui(root: Path) -> None:
    """A minimal Open WebUI data dir: webui.db with a `file` table + uploads/."""
    (root / "uploads").mkdir(parents=True)
    conn = sqlite3.connect(root / "webui.db")
    conn.execute(
        "CREATE TABLE file (id TEXT PRIMARY KEY, user_id TEXT, hash TEXT, filename TEXT, path TEXT, "
        "data JSON, meta JSON, access_control JSON, created_at BIGINT, updated_at BIGINT)"
    )
    conn.commit()
    conn.close()


def add_upload(root: Path, file_id: str, user_id: str, filename: str, data: bytes) -> None:
    path = root / "uploads" / f"{file_id}_{filename}"
    path.write_bytes(data)
    conn = sqlite3.connect(root / "webui.db")
    conn.execute(
        "INSERT INTO file (id, user_id, filename, path, meta, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (
            file_id,
            user_id,
            filename,
            f"/app/backend/data/uploads/{file_id}_{filename}",
            f'{{"size": {len(data)}, "content_type": "application/octet-stream"}}',
            int(time.time()),
        ),
    )
    conn.commit()
    conn.close()


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, Path]]:
    data, owui = tmp_path / "data", tmp_path / "owui"
    make_owui(owui)
    monkeypatch.setenv("TOOLS_API_KEY", API_KEY)
    monkeypatch.setenv("TOOLS_SIGNING_KEY", "sign")
    monkeypatch.setenv("TOOLS_PUBLIC_URL", "http://testserver")
    monkeypatch.setenv("TOOLS_DATA_DIR", str(data))
    monkeypatch.setenv("TOOLS_OWUI_DATA_DIR", str(owui))
    # Nothing listens here, so read_file exercises the local fallback readers.
    monkeypatch.setenv("TOOLS_DOCLING_URL", "http://127.0.0.1:9")
    from app import main
    from app.config import get_settings

    get_settings.cache_clear()
    main.get_ctx.cache_clear()
    yield {"data": data, "owui": owui}
    get_settings.cache_clear()
    main.get_ctx.cache_clear()


@pytest.fixture
def client(env: dict[str, Path]) -> TestClient:
    from app.main import app

    return TestClient(app)


def headers(user: str | None = ALICE, role: str = "user") -> dict[str, str]:
    h = {"Authorization": f"Bearer {API_KEY}"}
    if user:
        h["X-OpenWebUI-User-Id"] = user
        h["X-OpenWebUI-User-Role"] = role
    return h
