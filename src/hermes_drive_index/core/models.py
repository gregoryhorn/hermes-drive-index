"""Data models and constants for Drive indexing."""

from __future__ import annotations

from dataclasses import dataclass

GOOGLE_FOLDER = "application/vnd.google-apps.folder"
GOOGLE_DOC = "application/vnd.google-apps.document"
GOOGLE_SHEET = "application/vnd.google-apps.spreadsheet"
GOOGLE_SLIDE = "application/vnd.google-apps.presentation"
PHOTO_PREFIX = "image/"
VIDEO_PREFIX = "video/"
IMAGE_OCR_MIMES = {"image/png", "image/jpeg", "image/tiff", "image/bmp", "image/webp"}

INDEXABLE_MIMES = {
    "application/pdf",
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/json",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    GOOGLE_DOC,
    GOOGLE_SHEET,
    GOOGLE_SLIDE,
}


@dataclass
class DriveFile:
    id: str
    name: str
    mime_type: str
    path: str
    size: int
    modified_time: str | None
    md5_checksum: str | None
    web_view_link: str | None
    parents: tuple[str, ...] = ()


def is_indexable(f: DriveFile, *, ocr_image_enabled: bool = False) -> bool:
    if f.mime_type == GOOGLE_FOLDER:
        return False
    if f.mime_type.startswith(VIDEO_PREFIX):
        return False
    if f.mime_type.startswith(PHOTO_PREFIX):
        return ocr_image_enabled and f.mime_type in IMAGE_OCR_MIMES
    return f.mime_type in INDEXABLE_MIMES or f.mime_type.startswith("text/")
