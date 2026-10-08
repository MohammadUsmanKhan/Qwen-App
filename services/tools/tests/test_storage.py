from __future__ import annotations

import time
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import pytest

from app.errors import ToolError
from app.storage import FileStore, safe_filename


def store(tmp_path: Path, ttl: int = 1) -> FileStore:
    return FileStore(tmp_path, "secret", "http://h:8001/", ttl)


def parts(url: str) -> tuple[str, str, int, str]:
    u = urlparse(url)
    _, _, fid, name = u.path.split("/")
    q = parse_qs(u.query)
    return fid, unquote(name), int(q["exp"][0]), q["sig"][0]


def test_save_get_and_signed_link(tmp_path: Path) -> None:
    s = store(tmp_path)
    sf = s.save_bytes(b"hello", "My Report.docx", user="u1", kind="docx", extra={"k": 1})
    assert sf.file_id.startswith("gen_")
    got = s.get(sf.file_id)
    assert got.path.read_bytes() == b"hello" and got.extra == {"k": 1} and got.user == "u1"
    url = s.download_url(sf)
    assert url.startswith("http://h:8001/files/")
    fid, name, exp, sig = parts(url)
    assert s.verify(fid, name, exp, sig).file_id == sf.file_id


def test_tampered_and_expired_links(tmp_path: Path) -> None:
    s = store(tmp_path)
    sf = s.save_bytes(b"x", "a.docx", user=None, kind="docx")
    fid, name, exp, sig = parts(s.download_url(sf))
    with pytest.raises(ToolError, match="Invalid"):
        s.verify(fid, name, exp + 1, sig)
    with pytest.raises(ToolError, match="expired"):
        s.verify(fid, name, int(time.time()) - 1, s._sig(fid, name, int(time.time()) - 1))


def test_new_version_replaces_old(tmp_path: Path) -> None:
    s = store(tmp_path)
    sf = s.save_bytes(b"v1", "a.docx", user=None, kind="docx")
    s.save_bytes(b"v2", "a.docx", user=None, kind="docx", file_id=sf.file_id)
    assert s.get(sf.file_id).path.read_bytes() == b"v2"


def test_bad_ids_and_filenames(tmp_path: Path) -> None:
    s = store(tmp_path)
    for bad in ("../etc", "gen_../../x", "gen_zz"):
        with pytest.raises(ToolError):
            s.get(bad)
    assert safe_filename('a/b:c*?"d', ".docx") == "a b c d.docx"
    assert safe_filename("  ", ".docx") == "file.docx"
