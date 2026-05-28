"""Google Drive crawling and download/export helpers."""

from __future__ import annotations

from pathlib import Path
import re
import sys
from typing import Any

from .models import DriveFile, GOOGLE_DOC, GOOGLE_FOLDER, GOOGLE_SHEET, GOOGLE_SLIDE


def build_drive_service(google_api_dir: Path) -> Any:
    sys.path.insert(0, str(google_api_dir))
    import google_api  # type: ignore

    return google_api.build_service("drive", "v3")


def crawl(service: Any, root_id: str, root_name: str) -> list[DriveFile]:
    stack = [(root_id, root_name)]
    out: list[DriveFile] = []
    while stack:
        folder_id, folder_path = stack.pop()
        page = None
        while True:
            resp = service.files().list(
                q=f"'{folder_id}' in parents and trashed=false",
                spaces="drive",
                fields="nextPageToken, files(id,name,mimeType,size,modifiedTime,md5Checksum,webViewLink,parents)",
                pageSize=1000,
                pageToken=page,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            ).execute()
            for f in resp.get("files", []):
                path = f"{folder_path}/{f.get('name','')}"
                df = DriveFile(
                    id=f["id"],
                    name=f.get("name", ""),
                    mime_type=f.get("mimeType", ""),
                    path=path,
                    size=int(f.get("size") or 0),
                    modified_time=f.get("modifiedTime"),
                    md5_checksum=f.get("md5Checksum"),
                    web_view_link=f.get("webViewLink"),
                )
                out.append(df)
                if df.mime_type == GOOGLE_FOLDER:
                    stack.append((df.id, path))
            page = resp.get("nextPageToken")
            if not page:
                break
    return out


def cache_path(cache_dir: Path, f: DriveFile, suffix: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", f.name)[:80]
    return cache_dir / f"{f.id}_{safe}{suffix}"


def export_suffix(f: DriveFile) -> str:
    if f.mime_type in {GOOGLE_DOC, GOOGLE_SLIDE}:
        return ".txt"
    if f.mime_type == GOOGLE_SHEET:
        return ".csv"
    return Path(f.name).suffix or ".bin"


def download_or_export(service: Any, cache_dir: Path, f: DriveFile) -> Path | None:
    if f.mime_type in {GOOGLE_DOC, GOOGLE_SLIDE}:
        req = service.files().export_media(fileId=f.id, mimeType="text/plain")
        out = cache_path(cache_dir, f, ".txt")
    elif f.mime_type == GOOGLE_SHEET:
        req = service.files().export_media(fileId=f.id, mimeType="text/csv")
        out = cache_path(cache_dir, f, ".csv")
    else:
        req = service.files().get_media(fileId=f.id, supportsAllDrives=True)
        out = cache_path(cache_dir, f, export_suffix(f))

    data = req.execute()
    out.write_bytes(data)
    return out
