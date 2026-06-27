"""Document text extraction and chunking."""

from __future__ import annotations

from pathlib import Path
import re

from .models import DriveFile, GOOGLE_DOC, GOOGLE_SHEET, GOOGLE_SLIDE
from .ocr import ocr_image, ocr_pdf

_LAST_TEXT_WAS_OCR = False


def text_was_ocr() -> bool:
    return _LAST_TEXT_WAS_OCR


def extract_pdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    parts = []
    for i, page in enumerate(reader.pages):
        try:
            txt = page.extract_text() or ""
        except Exception as e:
            txt = f"\n[page {i + 1} extraction error: {e}]\n"
        if txt.strip():
            parts.append(txt)
    return "\n\n".join(parts)


def extract_docx(path: Path) -> str:
    import docx

    d = docx.Document(str(path))
    return "\n".join(p.text for p in d.paragraphs if p.text.strip())


def extract_text(
    path: Path,
    f: DriveFile,
    *,
    ocr_pdf_enabled: bool = False,
    ocr_image_enabled: bool = False,
    ocr_pdf_args: tuple[str, ...] = (),
    ocr_image_args: tuple[str, ...] = (),
) -> str:
    global _LAST_TEXT_WAS_OCR
    _LAST_TEXT_WAS_OCR = False
    mt = f.mime_type
    if mt == "application/pdf":
        text = extract_pdf(path)
        if text.strip() or not ocr_pdf_enabled:
            return text
        ocr_text = ocr_pdf(path, extra_args=ocr_pdf_args) or ""
        _LAST_TEXT_WAS_OCR = bool(ocr_text.strip())
        return ocr_text
    if mt.startswith("image/"):
        if not ocr_image_enabled:
            return ""
        ocr_text = ocr_image(path, extra_args=ocr_image_args) or ""
        _LAST_TEXT_WAS_OCR = bool(ocr_text.strip())
        return ocr_text
    if mt == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return extract_docx(path)
    if mt == "application/msword":
        return ""
    if mt in {GOOGLE_DOC, GOOGLE_SLIDE, GOOGLE_SHEET} or mt.startswith("text/") or mt == "application/json":
        return path.read_text(errors="replace")
    return ""


def chunk_text(text: str, max_chars: int = 2400, overlap: int = 250) -> list[str]:
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    buf = ""
    for p in paras or [text.strip()]:
        if len(buf) + len(p) + 2 <= max_chars:
            buf = (buf + "\n\n" + p).strip()
        else:
            if buf:
                chunks.append(buf)
            if len(p) <= max_chars:
                buf = p
            else:
                start = 0
                while start < len(p):
                    chunks.append(p[start:start + max_chars])
                    start += max_chars - overlap
                buf = ""
    if buf:
        chunks.append(buf)
    return chunks
