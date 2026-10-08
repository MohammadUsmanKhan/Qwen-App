"""LibreOffice headless rendering: Office file → PDF → PNG pages.

Used for previews and (Phase 6) visual checks of reference-mode output.
Each call gets its own LibreOffice profile dir so parallel renders don't collide.
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path

from .errors import ToolError


async def _run(cmd: list[str], timeout: float) -> None:
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        _, err = await asyncio.wait_for(proc.communicate(), timeout)
    except TimeoutError as e:
        proc.kill()
        raise ToolError("render_timeout", f"{Path(cmd[0]).name} took longer than {timeout:.0f}s.") from e
    if proc.returncode != 0:
        raise ToolError("render_failed", f"{Path(cmd[0]).name} failed: {err.decode(errors='replace')[:300]}")


async def to_pdf(src: Path, out_dir: Path, soffice: str = "soffice", timeout: float = 180) -> Path:
    if not shutil.which(soffice):
        raise ToolError("renderer_missing", "LibreOffice is not installed in the tool server.")
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="lo-profile-") as profile:
        await _run(
            [
                soffice,
                f"-env:UserInstallation=file://{profile}",
                "--headless",
                "--norestore",
                "--convert-to",
                "pdf",
                "--outdir",
                str(out_dir),
                str(src),
            ],
            timeout,
        )
    pdf = out_dir / (src.stem + ".pdf")
    if not pdf.exists():
        raise ToolError("render_failed", f"LibreOffice produced no PDF for {src.name}.")
    return pdf


async def pdf_to_pngs(
    pdf: Path, out_dir: Path, dpi: int = 80, first: int | None = None, last: int | None = None, timeout: float = 120
) -> list[Path]:
    if not shutil.which("pdftoppm"):
        raise ToolError("renderer_missing", "pdftoppm (poppler-utils) is not installed.")
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = ["pdftoppm", "-png", "-r", str(dpi)]
    if first:
        cmd += ["-f", str(first)]
    if last:
        cmd += ["-l", str(last)]
    await _run(cmd + [str(pdf), str(out_dir / "page")], timeout)
    return sorted(out_dir.glob("page-*.png"), key=lambda p: int(p.stem.rsplit("-", 1)[1]))


async def render_pages(
    src: Path,
    out_dir: Path,
    *,
    soffice: str = "soffice",
    dpi: int = 80,
    max_pages: int | None = None,
    timeout: float = 180,
) -> list[Path]:
    pdf = src if src.suffix.lower() == ".pdf" else await to_pdf(src, out_dir, soffice, timeout)
    return await pdf_to_pngs(pdf, out_dir, dpi=dpi, first=1 if max_pages else None, last=max_pages)
