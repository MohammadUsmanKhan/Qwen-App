from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

from fastapi.testclient import TestClient

from .conftest import ALICE, BOB, add_upload, headers
from .samples import docx_bytes

DOC = {
    "title": "Site Survey",
    "blocks": [{"type": "heading", "text": "Scope", "level": 1}, {"type": "paragraph", "text": "Hello"}],
}


def test_requires_api_key(client: TestClient) -> None:
    r = client.post("/tools/create_document", json=DOC)
    assert r.status_code == 401


def test_openapi_is_inlined_and_named(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    text = json.dumps(schema["paths"])
    assert "$ref" not in text
    ops = {op["operationId"] for p in schema["paths"].values() for op in p.values()}
    assert ops == {"list_uploaded_files", "read_file", "create_document", "append_document_section"}


def test_create_document_and_download(client: TestClient, env: dict[str, Path]) -> None:
    r = client.post("/tools/create_document", json=DOC, headers=headers()).json()
    assert r["ok"] is True
    assert r["filename"] == "Site Survey.docx"
    assert r["markdown_link"].startswith("[Site Survey.docx](http://testserver/files/")
    assert r["summary"]["sections"] == ["Scope"]
    url = urlparse(r["download_url"])
    dl = client.get(f"{url.path}?{url.query}")
    assert dl.status_code == 200 and dl.content[:2] == b"PK"
    bad = client.get(f"{url.path}?{url.query.replace('sig=', 'sig=00')}")
    assert bad.status_code == 403
    log = (env["data"] / "logs" / "tool_calls.jsonl").read_text().strip().splitlines()
    entry = json.loads(log[-1])
    assert entry["tool"] == "create_document" and entry["ok"] and entry["user"] == ALICE


def test_append_section(client: TestClient) -> None:
    first = client.post("/tools/create_document", json=DOC, headers=headers()).json()
    r = client.post(
        "/tools/append_document_section",
        headers=headers(),
        json={
            "file_id": first["file_id"],
            "blocks": [{"type": "heading", "text": "Findings", "level": 1}, {"type": "markdown", "text": "## Costs"}],
        },
    ).json()
    assert r["ok"] and r["file_id"] == first["file_id"]
    assert r["summary"]["sections"] == ["Scope", "Findings", "  Costs"]
    other = client.post(
        "/tools/append_document_section",
        headers=headers(BOB),
        json={"file_id": first["file_id"], "blocks": [{"type": "paragraph", "text": "x"}]},
    ).json()
    assert other["ok"] is False and other["error"]["code"] == "not_found"


def test_invalid_arguments_are_structured(client: TestClient, env: dict[str, Path]) -> None:
    r = client.post(
        "/tools/create_document",
        headers=headers(),
        json={"title": "x", "blocks": [{"type": "heading", "text": "H", "level": 7}]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False and body["error"]["code"] == "invalid_arguments"
    assert "level" in body["error"]["message"] and body["error"]["hint"]


def test_list_and_read_uploads(client: TestClient, env: dict[str, Path]) -> None:
    add_upload(env["owui"], "f-alice", ALICE, "review.docx", docx_bytes())
    add_upload(env["owui"], "f-bob", BOB, "secret.txt", b"bob only")
    listed = client.post("/tools/list_uploaded_files", json={}, headers=headers()).json()
    assert [f["file_id"] for f in listed["files"]] == ["f-alice"]

    r = client.post("/tools/read_file", json={"file_id": "f-alice"}, headers=headers()).json()
    assert r["ok"] and r["filename"] == "review.docx" and "Quarterly Review" in r["content"]
    assert r["next_offset"] is None

    denied = client.post("/tools/read_file", json={"file_id": "f-bob"}, headers=headers()).json()
    assert denied["ok"] is False and denied["error"]["code"] == "not_found"
    admin = client.post("/tools/read_file", json={"file_id": "f-bob"}, headers=headers(role="admin")).json()
    assert admin["ok"] and admin["content"] == "bob only"


def test_read_requires_user_header(client: TestClient, env: dict[str, Path]) -> None:
    add_upload(env["owui"], "f1", ALICE, "a.txt", b"x")
    r = client.post("/tools/read_file", json={"file_id": "f1"}, headers=headers(user=None)).json()
    assert r["ok"] is False and r["error"]["code"] == "user_unknown"


def test_read_paging(client: TestClient, env: dict[str, Path]) -> None:
    add_upload(env["owui"], "long", ALICE, "long.txt", b"abcdefghij" * 300)
    r = client.post("/tools/read_file", json={"file_id": "long", "max_chars": 1000}, headers=headers()).json()
    assert len(r["content"]) == 1000 and r["next_offset"] == 1000 and r["chars_total"] == 3000
    r2 = client.post(
        "/tools/read_file", json={"file_id": "long", "offset": 2500, "max_chars": 1000}, headers=headers()
    ).json()
    assert len(r2["content"]) == 500 and r2["next_offset"] is None


def test_generated_file_can_be_read_and_embedded(client: TestClient, env: dict[str, Path]) -> None:
    from PIL import Image

    from app.main import get_ctx

    img = env["data"] / "x.png"
    img.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (50, 50), "blue").save(img)
    sf = get_ctx().store.save_file(img, "chart.png", user=ALICE, kind="image")
    r = client.post(
        "/tools/create_document",
        headers=headers(),
        json={"title": "With image", "blocks": [{"type": "image", "file_id": sf.file_id}]},
    ).json()
    assert r["ok"] and r["summary"]["images"] == 1 and r["warnings"] == []
    read = client.post("/tools/read_file", json={"file_id": r["file_id"]}, headers=headers()).json()
    assert read["ok"] and "With image" in read["content"]
