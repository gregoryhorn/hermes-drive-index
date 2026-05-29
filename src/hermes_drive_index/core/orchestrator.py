"""Index build/update orchestration."""

from __future__ import annotations

from pathlib import Path
import json
import sqlite3
import time
import uuid

from hermes_drive_index.config import DriveIndexConfig
from .crawler import build_drive_service, crawl
from .index import existing_files, index_file, init_db, insert_skipped_file, delete_file_from_index, migrate, update_file_metadata
from .manifest import plan_incremental_actions
from .models import is_indexable
from .search import search_db, status_db
from .utils import now_iso


def ensure_dirs(cfg: DriveIndexConfig) -> None:
    cfg.base_dir.mkdir(parents=True, exist_ok=True)
    cfg.cache_dir.mkdir(parents=True, exist_ok=True)


def _root_id(cfg: DriveIndexConfig) -> str:
    if not cfg.root_folder_id:
        raise ValueError("Drive index root_folder_id is not configured. Set HERMES_DRIVE_INDEX_ROOT_FOLDER_ID or local config.toml.")
    return cfg.root_folder_id


def _base_metrics(run_id: str, started_at: str, mode: str, files_scanned: int) -> dict:
    return {
        "run_id": run_id,
        "started_at": started_at,
        "mode": mode,
        "files_scanned": files_scanned,
        "files_indexed": 0,
        "files_skipped": 0,
        "files_failed": 0,
        "bytes_downloaded": 0,
        "chunks": 0,
        "files_indexed_native": 0,
        "files_indexed_ocr": 0,
        "files_metadata_only": 0,
        "ocr_attempted": 0,
        "ocr_failed": 0,
        "ocr_skipped_unavailable": 0,
        "errors": [],
    }


def build_index(cfg: DriveIndexConfig) -> dict:
    ensure_dirs(cfg)
    service = build_drive_service(cfg.google_api_dir)
    start = time.time()
    run_id = str(uuid.uuid4())
    files = crawl(service, _root_id(cfg), cfg.root_folder_name)
    tmp = cfg.base_dir / "index.new.db"
    if tmp.exists():
        tmp.unlink()
    con = init_db(tmp)
    metrics = {
        "run_id": run_id,
        "started_at": now_iso(),
        "mode": "weekly_full_document_only",
        "files_scanned": len(files),
        "files_indexed": 0,
        "files_skipped": 0,
        "files_failed": 0,
        "bytes_downloaded": 0,
        "chunks": 0,
        "files_indexed_native": 0,
        "files_indexed_ocr": 0,
        "files_metadata_only": 0,
        "ocr_attempted": 0,
        "ocr_failed": 0,
        "ocr_skipped_unavailable": 0,
        "errors": [],
    }
    for f in files:
        if not is_indexable(f, ocr_image_enabled=cfg.ocr_image_enabled):
            metrics["files_skipped"] += 1
            insert_skipped_file(con, f)
            continue
        try:
            index_file(con, service, cfg.cache_dir, f, metrics, ocr_pdf_enabled=cfg.ocr_enabled, ocr_image_enabled=cfg.ocr_image_enabled)
            metrics["files_indexed"] += 1
        except Exception as e:
            metrics["files_failed"] += 1
            error = repr(e)
            metrics["errors"].append({"file_id": f.id, "path": f.path, "mime_type": f.mime_type, "error": error})
            con.execute("insert or replace into files values (?,?,?,?,?,?,?,?,?,?,?)", (f.id, f.name, f.path, f.mime_type, f.size, f.modified_time, f.md5_checksum, f.web_view_link, None, "failed", error))
        con.commit()
    finished = now_iso()
    duration = time.time() - start
    con.execute("insert into runs values (?,?,?,?,?,?,?,?,?,?,?)", (run_id, metrics["started_at"], finished, metrics["mode"], metrics["files_scanned"], metrics["files_indexed"], metrics["files_skipped"], metrics["files_failed"], metrics["bytes_downloaded"], metrics["chunks"], "success"))
    con.commit(); con.close()
    if cfg.db_path.exists():
        backup = cfg.base_dir / "index.previous.db"
        if backup.exists():
            backup.unlink()
        cfg.db_path.replace(backup)
    tmp.replace(cfg.db_path)
    metrics["finished_at"] = finished
    metrics["duration_seconds"] = round(duration, 2)
    metrics["index_db_bytes"] = cfg.db_path.stat().st_size
    (cfg.base_dir / "last_build_metrics.json").write_text(json.dumps(metrics, indent=2))
    return metrics


def incremental_update(cfg: DriveIndexConfig) -> dict:
    ensure_dirs(cfg)
    if not cfg.db_path.exists():
        result = build_index(cfg)
        result["fallback_reason"] = "index db did not exist"
        return result
    service = build_drive_service(cfg.google_api_dir)
    start = time.time()
    run_id = str(uuid.uuid4())
    files = crawl(service, _root_id(cfg), cfg.root_folder_name)
    files_by_id = {f.id: f for f in files}
    con = sqlite3.connect(cfg.db_path)
    con.row_factory = sqlite3.Row
    migrate(con)
    current = existing_files(con)
    plan = plan_incremental_actions(files, current, ocr_image_enabled=cfg.ocr_image_enabled)
    metrics = {
        "run_id": run_id,
        "started_at": now_iso(),
        "mode": "incremental_manifest",
        "files_scanned": len(files),
        "files_indexed": 0,
        "files_skipped": 0,
        "files_failed": 0,
        "bytes_downloaded": 0,
        "chunks": 0,
        "files_indexed_native": 0,
        "files_indexed_ocr": 0,
        "files_metadata_only": 0,
        "ocr_attempted": 0,
        "ocr_failed": 0,
        "ocr_skipped_unavailable": 0,
        "files_deleted": 0,
        "files_unchanged": len(plan["unchanged"]),
        "files_metadata_updated": 0,
        "files_reindexed": 0,
        "errors": [],
    }
    try:
        con.execute("begin")
        for file_id in plan["delete"]:
            delete_file_from_index(con, file_id)
            metrics["files_deleted"] += 1
        for file_id in plan["skip"]:
            insert_skipped_file(con, files_by_id[file_id])
            metrics["files_skipped"] += 1
        for file_id in plan["metadata_only"]:
            updated_chunks = update_file_metadata(con, files_by_id[file_id], current[file_id])
            metrics["files_metadata_updated"] += 1
            metrics["chunks"] += updated_chunks
        for file_id in plan["reindex"]:
            f = files_by_id[file_id]
            try:
                index_file(con, service, cfg.cache_dir, f, metrics, ocr_pdf_enabled=cfg.ocr_enabled, ocr_image_enabled=cfg.ocr_image_enabled)
                metrics["files_indexed"] += 1
                metrics["files_reindexed"] += 1
            except Exception as e:
                metrics["files_failed"] += 1
                error = repr(e)
                metrics["errors"].append({"file_id": f.id, "path": f.path, "mime_type": f.mime_type, "error": error})
                con.execute("insert or replace into files values (?,?,?,?,?,?,?,?,?,?,?)", (f.id, f.name, f.path, f.mime_type, f.size, f.modified_time, f.md5_checksum, f.web_view_link, None, "failed", error))
        finished = now_iso()
        duration = time.time() - start
        con.execute("insert into runs values (?,?,?,?,?,?,?,?,?,?,?)", (run_id, metrics["started_at"], finished, metrics["mode"], metrics["files_scanned"], metrics["files_indexed"], metrics["files_skipped"], metrics["files_failed"], metrics["bytes_downloaded"], metrics["chunks"], "success"))
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    metrics["finished_at"] = finished
    metrics["duration_seconds"] = round(duration, 2)
    metrics["index_db_bytes"] = cfg.db_path.stat().st_size
    metrics["plan_counts"] = {k: len(v) for k, v in plan.items()}
    (cfg.base_dir / "last_build_metrics.json").write_text(json.dumps(metrics, indent=2))
    return metrics


def reindex_metadata_only(cfg: DriveIndexConfig) -> dict:
    ensure_dirs(cfg)
    if not cfg.db_path.exists():
        raise FileNotFoundError(f"Index DB does not exist: {cfg.db_path}")
    service = build_drive_service(cfg.google_api_dir)
    start = time.time()
    run_id = str(uuid.uuid4())
    files = crawl(service, _root_id(cfg), cfg.root_folder_name)
    files_by_id = {f.id: f for f in files}
    con = sqlite3.connect(cfg.db_path)
    con.row_factory = sqlite3.Row
    migrate(con)
    current = existing_files(con)
    metadata_ids = [file_id for file_id, row in current.items() if row.get("status") == "indexed_metadata"]
    metrics = _base_metrics(run_id, now_iso(), "reindex_metadata_only", len(files))
    metrics.update({"files_considered": len(metadata_ids), "files_deleted": 0, "files_reindexed": 0})
    try:
        con.execute("begin")
        for file_id in metadata_ids:
            f = files_by_id.get(file_id)
            if f is None:
                delete_file_from_index(con, file_id)
                metrics["files_deleted"] += 1
                continue
            if not is_indexable(f, ocr_image_enabled=cfg.ocr_image_enabled):
                insert_skipped_file(con, f)
                metrics["files_skipped"] += 1
                continue
            try:
                index_file(con, service, cfg.cache_dir, f, metrics, ocr_pdf_enabled=cfg.ocr_enabled, ocr_image_enabled=cfg.ocr_image_enabled)
                metrics["files_indexed"] += 1
                metrics["files_reindexed"] += 1
            except Exception as e:
                metrics["files_failed"] += 1
                error = repr(e)
                metrics["errors"].append({"file_id": f.id, "path": f.path, "mime_type": f.mime_type, "error": error})
                con.execute("insert or replace into files values (?,?,?,?,?,?,?,?,?,?,?)", (f.id, f.name, f.path, f.mime_type, f.size, f.modified_time, f.md5_checksum, f.web_view_link, None, "failed", error))
        finished = now_iso()
        duration = time.time() - start
        con.execute("insert into runs values (?,?,?,?,?,?,?,?,?,?,?)", (run_id, metrics["started_at"], finished, metrics["mode"], metrics["files_scanned"], metrics["files_indexed"], metrics["files_skipped"], metrics["files_failed"], metrics["bytes_downloaded"], metrics["chunks"], "success"))
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    metrics["finished_at"] = finished
    metrics["duration_seconds"] = round(duration, 2)
    metrics["index_db_bytes"] = cfg.db_path.stat().st_size
    (cfg.base_dir / "last_build_metrics.json").write_text(json.dumps(metrics, indent=2))
    return metrics


def search(cfg: DriveIndexConfig, query: str, top_k: int = 8) -> dict:
    return search_db(cfg.db_path, query, top_k)


def status(cfg: DriveIndexConfig) -> dict:
    return status_db(cfg.db_path)
