"""Read-only privacy-preserving OCR benchmark helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import sqlite3
import tempfile
import time
import uuid

from hermes_drive_index.config import DriveIndexConfig
from .crawler import build_drive_service, crawl
from .index import existing_files, index_file, migrate
from .models import is_indexable
from .search import search_db
from .utils import now_iso


@dataclass(frozen=True)
class OcrBenchmarkMode:
    """OCR parameter set to test against metadata-only candidates."""

    name: str
    pdf_args: tuple[str, ...] = ()
    image_args: tuple[str, ...] = ()


DEFAULT_OCR_BENCHMARK_MODES: tuple[OcrBenchmarkMode, ...] = (
    OcrBenchmarkMode("ocr_default"),
    OcrBenchmarkMode("rotate_deskew", pdf_args=("--rotate-pages", "--deskew")),
    OcrBenchmarkMode("rotate_deskew_clean", pdf_args=("--rotate-pages", "--deskew", "--remove-background")),
    OcrBenchmarkMode(
        "dpi300_psm6",
        pdf_args=("--image-dpi", "300", "--tesseract-pagesegmode", "6"),
        image_args=("--dpi", "300", "--psm", "6", "--oem", "1"),
    ),
)


_AGGREGATE_STATUSES = ("indexed", "indexed_ocr", "indexed_metadata", "skipped", "failed")


def _counts_for_ids(con: sqlite3.Connection, file_ids: list[str]) -> dict[str, int]:
    counts = {status: 0 for status in _AGGREGATE_STATUSES}
    if not file_ids:
        return counts
    placeholders = ",".join("?" for _ in file_ids)
    rows = con.execute(
        f"select status, count(*) as c from files where file_id in ({placeholders}) group by status",
        file_ids,
    ).fetchall()
    for row in rows:
        status = row["status"] if isinstance(row, sqlite3.Row) else row[0]
        count = row["c"] if isinstance(row, sqlite3.Row) else row[1]
        counts[str(status)] = int(count)
    return counts


def _golden_rows(golden_path: Path | None) -> list[dict]:
    if golden_path is None or not golden_path.exists():
        return []
    rows = json.loads(golden_path.read_text())
    return rows if isinstance(rows, list) else []


def _rank_for_expected(results: list[dict], expected: str) -> int | None:
    for i, row in enumerate(results, start=1):
        # Private expected paths and result paths are used only in-process. They
        # are never returned by this benchmark; only aggregate recall/MRR is.
        haystack = row.get("path") or row.get("drive_path") or row.get("name") or ""
        if expected in haystack:
            return i
    return None


def _eval_aggregate(db_path: Path, golden: list[dict]) -> dict:
    if not golden:
        return {"queries": 0, "recall_at_5": None, "mrr": None}
    ranks: list[int | None] = []
    for row in golden:
        query = str(row.get("query") or "")
        expected = str(row.get("expected_path_contains") or "")
        if not query or not expected:
            ranks.append(None)
            continue
        results = search_db(db_path, query, top_k=5).get("results", [])
        ranks.append(_rank_for_expected(results, expected))
    n = len(ranks)
    recall_at_5 = sum(1 for rank in ranks if rank is not None and rank <= 5) / n
    mrr = sum((1 / rank) if rank else 0 for rank in ranks) / n
    return {"queries": n, "recall_at_5": round(recall_at_5, 3), "mrr": round(mrr, 3)}


def _delta(after: dict, before: dict, key: str) -> float | None:
    if before.get(key) is None or after.get(key) is None:
        return None
    return round(float(after[key]) - float(before[key]), 3)


def _base_mode_metrics(mode: OcrBenchmarkMode, candidate_count: int) -> dict:
    return {
        "mode": mode.name,
        "candidate_count": candidate_count,
        "files_considered": candidate_count,
        "files_reindexed": 0,
        "files_indexed": 0,
        "files_indexed_native": 0,
        "files_indexed_ocr": 0,
        "files_metadata_only": 0,
        "files_skipped": 0,
        "files_missing_from_crawl": 0,
        "files_failed": 0,
        "bytes_downloaded": 0,
        "chunks": 0,
        "ocr_attempted": 0,
        "ocr_failed": 0,
        "ocr_skipped_unavailable": 0,
    }


def _select_modes(names: list[str] | None) -> tuple[OcrBenchmarkMode, ...]:
    if not names:
        return DEFAULT_OCR_BENCHMARK_MODES
    by_name = {mode.name: mode for mode in DEFAULT_OCR_BENCHMARK_MODES}
    missing = [name for name in names if name not in by_name]
    if missing:
        raise ValueError(f"Unknown OCR benchmark mode(s): {', '.join(missing)}")
    return tuple(by_name[name] for name in names)


def _copy_sqlite_db(source: Path, target: Path) -> None:
    src = sqlite3.connect(source)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def benchmark_ocr_parameters(
    cfg: DriveIndexConfig,
    *,
    modes: list[str] | None = None,
    limit: int | None = None,
    golden_path: Path | None = None,
) -> dict:
    """Benchmark OCR options on metadata-only candidates with aggregate output.

    The production index DB and Google Drive files are not mutated. Candidate
    re-indexing happens in temporary DB/cache directories, and the returned
    payload intentionally excludes filenames, paths, snippets, OCR text, and
    Drive IDs.
    """
    if not cfg.db_path.exists():
        raise FileNotFoundError(f"Index DB does not exist: {cfg.db_path}")

    started = time.time()
    selected_modes = _select_modes(modes)
    golden = _golden_rows(golden_path)

    source_con = sqlite3.connect(cfg.db_path)
    source_con.row_factory = sqlite3.Row
    migrate(source_con)
    current = existing_files(source_con)
    candidate_ids = [file_id for file_id, row in current.items() if row.get("status") == "indexed_metadata"]
    if limit is not None:
        candidate_ids = candidate_ids[: max(0, limit)]
    before_counts = _counts_for_ids(source_con, candidate_ids)
    source_con.close()

    baseline_eval = _eval_aggregate(cfg.db_path, golden)

    service = build_drive_service(cfg.google_api_dir)
    files = crawl(service, cfg.root_folder_id or "", cfg.root_folder_name)
    files_by_id = {f.id: f for f in files}

    mode_results = []
    with tempfile.TemporaryDirectory(prefix="hermes-drive-index-ocr-benchmark-") as tmpdir:
        tmp_root = Path(tmpdir)
        for mode in selected_modes:
            mode_start = time.time()
            mode_db = tmp_root / f"{mode.name}.db"
            mode_cache = tmp_root / f"cache-{mode.name}"
            mode_cache.mkdir(parents=True, exist_ok=True)
            _copy_sqlite_db(cfg.db_path, mode_db)
            con = sqlite3.connect(mode_db)
            con.row_factory = sqlite3.Row
            migrate(con)
            metrics = _base_mode_metrics(mode, len(candidate_ids))
            try:
                con.execute("begin")
                for file_id in candidate_ids:
                    f = files_by_id.get(file_id)
                    if f is None:
                        metrics["files_missing_from_crawl"] += 1
                        continue
                    if not is_indexable(f, ocr_image_enabled=cfg.ocr_image_enabled):
                        metrics["files_skipped"] += 1
                        continue
                    try:
                        index_file(
                            con,
                            service,
                            mode_cache,
                            f,
                            metrics,
                            ocr_pdf_enabled=True,
                            ocr_image_enabled=cfg.ocr_image_enabled,
                            ocr_pdf_args=mode.pdf_args,
                            ocr_image_args=mode.image_args,
                        )
                        metrics["files_reindexed"] += 1
                        metrics["files_indexed"] += 1
                    except Exception:
                        # Intentionally aggregate only. Do not collect exception
                        # strings because they can contain private local paths.
                        metrics["files_failed"] += 1
                con.commit()
            except Exception:
                con.rollback()
                raise
            after_counts = _counts_for_ids(con, candidate_ids)
            mode_eval = _eval_aggregate(mode_db, golden)
            con.close()
            mode_results.append(
                {
                    **metrics,
                    "after_status_counts": after_counts,
                    "conversions": {
                        "to_indexed": after_counts.get("indexed", 0) - before_counts.get("indexed", 0),
                        "to_indexed_ocr": after_counts.get("indexed_ocr", 0) - before_counts.get("indexed_ocr", 0),
                        "remaining_indexed_metadata": after_counts.get("indexed_metadata", 0),
                    },
                    "runtime_seconds": round(time.time() - mode_start, 2),
                    "evaluation": mode_eval,
                    "evaluation_delta": {
                        "recall_at_5": _delta(mode_eval, baseline_eval, "recall_at_5"),
                        "mrr": _delta(mode_eval, baseline_eval, "mrr"),
                    },
                }
            )

    return {
        "run_id": str(uuid.uuid4()),
        "started_at": now_iso(),
        "mode": "ocr_parameter_benchmark_read_only",
        "read_only": True,
        "privacy": {
            "aggregate_only": True,
            "omits_filenames_paths_drive_ids_snippets_and_ocr_text": True,
            "temporary_workspaces_removed": True,
        },
        "candidate_count": len(candidate_ids),
        "before_status_counts": before_counts,
        "evaluation_baseline": baseline_eval,
        "modes": mode_results,
        "files_failed": sum(mode["files_failed"] for mode in mode_results),
        "duration_seconds": round(time.time() - started, 2),
    }
