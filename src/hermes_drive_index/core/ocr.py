"""Optional OCR helpers.

OCR is deliberately binary-driven and best-effort so the default package keeps no
hard OCR dependencies. Missing tools, timeouts, and command failures return
``None`` rather than raising into index builds.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile


def ocr_available(kind: str) -> bool:
    """Return whether the external OCR tool for ``kind`` is available."""
    if kind == "pdf":
        return shutil.which("ocrmypdf") is not None
    if kind == "image":
        return shutil.which("tesseract") is not None
    return False


def ocr_pdf(path: Path, *, timeout: int = 120, extra_args: tuple[str, ...] = ()) -> str | None:
    """OCR a scanned PDF and return its extracted text, or ``None`` on failure."""
    if not ocr_available("pdf"):
        return None
    try:
        from .extract import extract_pdf

        with tempfile.TemporaryDirectory(prefix="hermes-drive-index-ocr-") as tmpdir:
            out = Path(tmpdir) / "ocr.pdf"
            subprocess.run(
                ["ocrmypdf", "--skip-text", "--quiet", *extra_args, str(path), str(out)],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=timeout,
            )
            text = extract_pdf(out)
            return text if text.strip() else None
    except Exception:
        return None


def ocr_image(path: Path, *, timeout: int = 120, extra_args: tuple[str, ...] = ()) -> str | None:
    """OCR an image and return text, or ``None`` on failure."""
    if not ocr_available("image"):
        return None
    try:
        proc = subprocess.run(
            ["tesseract", str(path), "stdout", "--quiet", *extra_args],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=timeout,
        )
        return proc.stdout if proc.stdout.strip() else None
    except Exception:
        return None
