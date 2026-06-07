"""Optional Drive document auto-organization.

The organizer is intentionally conservative:

* disabled by default;
* only considers newly discovered files during incremental/full index runs;
* only touches indexable document files, not folders/photos/videos by default;
* supports dry-run mode for safe validation;
* records planned/applied actions in build metrics.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Iterable

from .models import DriveFile, is_indexable


@dataclass(frozen=True)
class OrganizeRule:
    """A filename/path matching rule for Drive auto-organization."""

    name: str
    pattern: str
    target_folder_path: str
    category: str | None = None
    rename_template: str | None = None


@dataclass(frozen=True)
class OrganizeConfig:
    """Resolved auto-organization configuration."""

    enabled: bool = False
    dry_run: bool = True
    apply_to_existing: bool = False
    default_target_folder_path: str | None = None
    rename_template: str = "{date} - {category} - {title}{ext}"
    rules: tuple[OrganizeRule, ...] = ()


def normalize_title(value: str) -> str:
    """Return a clean title fragment safe for Drive filenames."""

    stem = Path(value).stem
    stem = re.sub(r"[_\-]+", " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip()
    stem = re.sub(r"[^\w\s.,&()+]", "", stem, flags=re.UNICODE).strip()
    return stem[:90] or "Document"


def extension_for_file(f: DriveFile) -> str:
    """Return native filename extension when useful."""

    suffix = Path(f.name).suffix
    if suffix:
        return suffix
    if f.mime_type == "application/pdf":
        return ".pdf"
    if f.mime_type in {
        "application/vnd.google-apps.document",
        "application/vnd.google-apps.spreadsheet",
        "application/vnd.google-apps.presentation",
    }:
        return ""
    return ""


def date_for_file(f: DriveFile) -> str:
    """Use Drive modified date as a stable fallback date."""

    if f.modified_time and len(f.modified_time) >= 10:
        return f.modified_time[:10]
    return "undated"


def first_matching_rule(f: DriveFile, rules: Iterable[OrganizeRule]) -> OrganizeRule | None:
    haystack = f"{f.path}\n{f.name}"
    for rule in rules:
        if re.search(rule.pattern, haystack, flags=re.IGNORECASE):
            return rule
    return None


def render_name(f: DriveFile, *, category: str, template: str) -> str:
    title = normalize_title(f.name)
    ext = extension_for_file(f)
    # Avoid duplicate extension when title already came from filename stem.
    rendered = template.format(
        date=date_for_file(f),
        category=category,
        title=title,
        ext=ext,
        original_name=f.name,
        mime_type=f.mime_type,
    )
    rendered = re.sub(r"\s+", " ", rendered).strip()
    rendered = re.sub(r"[\\/:*?\"<>|]+", "-", rendered).strip(" .-")
    return rendered[:180] or f.name


def plan_organize_file(f: DriveFile, cfg: OrganizeConfig) -> dict | None:
    """Return an organization action for a file, or None if no action applies."""

    if not cfg.enabled:
        return None
    if not is_indexable(f):
        return None
    rule = first_matching_rule(f, cfg.rules)
    target_path = rule.target_folder_path if rule else cfg.default_target_folder_path
    if not target_path:
        return None
    category = (rule.category if rule and rule.category else Path(target_path).name) or "Document"
    template = rule.rename_template if rule and rule.rename_template else cfg.rename_template
    new_name = render_name(f, category=category, template=template)
    current_folder_path = str(Path(f.path).parent)
    needs_rename = new_name != f.name
    needs_move = current_folder_path != target_path
    if not needs_rename and not needs_move:
        return None
    return {
        "file_id": f.id,
        "old_name": f.name,
        "new_name": new_name,
        "old_path": f.path,
        "target_folder_path": target_path,
        "rule": rule.name if rule else "default",
        "dry_run": cfg.dry_run,
        "needs_rename": needs_rename,
        "needs_move": needs_move,
    }


def drive_query_string(value: str) -> str:
    """Escape a value for a single-quoted Google Drive query string."""

    return value.replace("\\", "\\\\").replace("'", "\\'")


def ensure_folder_path(service: Any, root_id: str, root_name: str, target_path: str) -> str:
    """Ensure a target folder path exists below the configured root and return folder ID."""

    parts = [p for p in Path(target_path).parts if p not in {"/", root_name}]
    parent_id = root_id
    for part in parts:
        q = (
            f"'{drive_query_string(parent_id)}' in parents and trashed=false and "
            "mimeType='application/vnd.google-apps.folder' and "
            f"name='{drive_query_string(part)}'"
        )
        resp = service.files().list(
            q=q,
            spaces="drive",
            fields="files(id,name)",
            pageSize=10,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        files = resp.get("files", [])
        if files:
            parent_id = files[0]["id"]
            continue
        created = service.files().create(
            body={"name": part, "mimeType": "application/vnd.google-apps.folder", "parents": [parent_id]},
            fields="id,name",
            supportsAllDrives=True,
        ).execute()
        parent_id = created["id"]
    return parent_id


def apply_organize_action(service: Any, root_id: str, root_name: str, f: DriveFile, action: dict) -> dict:
    """Apply a planned organization action through the Drive API."""

    if action.get("dry_run"):
        return {**action, "applied": False}
    body: dict[str, Any] = {}
    if action.get("needs_rename"):
        body["name"] = action["new_name"]
    kwargs: dict[str, Any] = {"fileId": f.id, "body": body, "fields": "id,name,parents", "supportsAllDrives": True}
    if action.get("needs_move"):
        target_id = ensure_folder_path(service, root_id, root_name, action["target_folder_path"])
        current_parents = ",".join(getattr(f, "parents", ()) or ())
        kwargs["addParents"] = target_id
        if current_parents:
            kwargs["removeParents"] = current_parents
    updated = service.files().update(**kwargs).execute()
    return {**action, "applied": True, "drive_result": updated}


def organize_files(service: Any, root_id: str, root_name: str, files: Iterable[DriveFile], cfg: OrganizeConfig) -> dict:
    """Plan/apply organization actions for a collection of files."""

    metrics = {"enabled": cfg.enabled, "dry_run": cfg.dry_run, "planned": 0, "applied": 0, "errors": [], "actions": []}
    if not cfg.enabled:
        return metrics
    for f in files:
        action = plan_organize_file(f, cfg)
        if not action:
            continue
        metrics["planned"] += 1
        try:
            result = apply_organize_action(service, root_id, root_name, f, action)
            if result.get("applied"):
                metrics["applied"] += 1
            metrics["actions"].append(result)
        except Exception as exc:
            metrics["errors"].append({"file_id": f.id, "path": f.path, "error": repr(exc), "action": action})
    return metrics
