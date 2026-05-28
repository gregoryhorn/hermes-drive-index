"""Incremental update planning."""

from __future__ import annotations

from .models import DriveFile, GOOGLE_DOC, GOOGLE_SHEET, GOOGLE_SLIDE, is_indexable


def file_changed(f: DriveFile, existing: dict | None) -> bool:
    if existing is None:
        return True
    if existing.get("status") in {"failed"}:
        return True
    if f.mime_type in {GOOGLE_DOC, GOOGLE_SHEET, GOOGLE_SLIDE}:
        return f.modified_time != existing.get("modified_time")
    if f.md5_checksum or existing.get("md5_checksum"):
        return f.md5_checksum != existing.get("md5_checksum")
    return f.modified_time != existing.get("modified_time") or f.size != (existing.get("size_bytes") or 0)


def plan_incremental_actions(files: list[DriveFile], current: dict[str, dict]) -> dict[str, list[str]]:
    crawled_ids = {f.id for f in files}
    plan = {"reindex": [], "metadata_only": [], "unchanged": [], "skip": [], "delete": sorted(set(current) - crawled_ids)}
    for f in files:
        old = current.get(f.id)
        if not is_indexable(f):
            if old is None or old.get("name") != f.name or old.get("path") != f.path or old.get("mime_type") != f.mime_type:
                plan["skip"].append(f.id)
            else:
                plan["unchanged"].append(f.id)
            continue
        if file_changed(f, old):
            plan["reindex"].append(f.id)
        elif old and (old.get("name") != f.name or old.get("path") != f.path or old.get("web_view_link") != f.web_view_link):
            plan["metadata_only"].append(f.id)
        else:
            plan["unchanged"].append(f.id)
    return plan
