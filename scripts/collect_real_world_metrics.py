#!/usr/bin/env python3
"""Collect sanitized real-world Hermes Drive Index metrics.

Private raw metrics are appended locally under ~/.hermes/drive_index/metrics.
The public summary intentionally keeps only aggregate counts/latencies/eval scores.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import platform
import re
import shutil
import statistics
import subprocess
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_METRICS_DIR = Path.home() / ".hermes" / "drive_index" / "metrics"
RAW_JSONL = DEFAULT_METRICS_DIR / "hermes-drive-index-metrics.jsonl"
PUBLIC_SUMMARY = DEFAULT_METRICS_DIR / "latest-public-summary.json"
DB_PATH = Path.home() / ".hermes" / "drive_index" / "personal_files" / "index.db"
EVAL_JSON = Path.home() / ".hermes" / "drive_index" / "personal_files" / "eval" / "latest_eval.json"
SAFE_GENERIC_QUERIES = ["receipt", "invoice", "policy", "lease", "document"]

PRIVATE_PATH_RE = re.compile(r"/(?:home|Users)/[^\s\"']+|\.hermes/drive_index/personal_files")
DRIVE_ID_RE = re.compile(r"\b[A-Za-z0-9_-]{25,}\b")
RAW_RESULT_KEY_RE = re.compile(r'"(?:snippet|top_results|file_id|drive_id|web_view_link|name|path)"\s*:')


def stable_json(obj: Any) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False)


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _run_json(command: list[str], *, timeout: int = 60) -> tuple[dict[str, Any] | None, str | None]:
    try:
        completed = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True, timeout=timeout, check=False)
    except Exception as exc:  # noqa: BLE001 - collection should fail closed into reason fields
        return None, f"command failed to start: {exc}"
    if completed.returncode != 0:
        return None, f"exit {completed.returncode}: {(completed.stderr or completed.stdout).strip()[:500]}"
    try:
        return json.loads(completed.stdout), None
    except json.JSONDecodeError as exc:
        return None, f"invalid json: {exc}"


def _git_commit() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, text=True).strip()
    except Exception:
        return None


def _package_version() -> str | None:
    try:
        return metadata.version("hermes-drive-index")
    except metadata.PackageNotFoundError:
        init_file = REPO_ROOT / "src" / "hermes_drive_index" / "__init__.py"
        text = init_file.read_text(errors="ignore") if init_file.exists() else ""
        match = re.search(r"__version__\s*=\s*['\"]([^'\"]+)", text)
        return match.group(1) if match else None


def _package_install_mode() -> dict[str, Any]:
    result: dict[str, Any] = {"available": True}
    try:
        dist = metadata.distribution("hermes-drive-index")
        direct_url = dist.read_text("direct_url.json")
        result["location"] = str(dist.locate_file(""))
        if direct_url:
            parsed = json.loads(direct_url)
            result["editable"] = bool(parsed.get("dir_info", {}).get("editable"))
            result["source_url"] = parsed.get("url")
        else:
            result["editable"] = False
    except Exception as exc:  # noqa: BLE001
        result = {"available": False, "reason": str(exc)}
    return result


def _collect_status() -> dict[str, Any]:
    obj, err = _run_json(["hermes-drive-index", "status", "--json"])
    if err:
        return {"available": False, "reason": err}
    return obj or {"available": False, "reason": "empty status"}


def _collect_search_latencies() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    reasons: list[str] = []
    for idx, query in enumerate(SAFE_GENERIC_QUERIES):
        obj, err = _run_json(["hermes-drive-index", "search", query, "--top", "5", "--json"], timeout=60)
        if err:
            reasons.append(f"generic_{idx}: {err}")
            continue
        results = obj.get("results", []) if obj else []
        rows.append(
            {
                "label": f"generic_{idx}",
                "query": query,
                "latency_ms": obj.get("latency_ms") if obj else None,
                "results_count": len(results),
                "deduped_by_file": obj.get("deduped_by_file") if obj else None,
                "raw_candidates": obj.get("raw_candidates") if obj else None,
            }
        )
    if not rows:
        return {"available": False, "reason": "; ".join(reasons) or "no search measurements"}
    payload: dict[str, Any] = {"available": True, "queries": rows}
    if reasons:
        payload["partial_reasons"] = reasons
    return payload


def _eval_index_summary(eval_obj: dict[str, Any]) -> dict[str, Any]:
    summary = eval_obj.get("summary", {}) if isinstance(eval_obj, dict) else {}
    index = dict(summary.get("index", {}) or {})
    if "mrr" not in index:
        reciprocals = []
        for row in eval_obj.get("results", []) or []:
            rank = ((row.get("index") or {}).get("rank"))
            if isinstance(rank, int) and rank > 0:
                reciprocals.append(1 / rank)
            else:
                reciprocals.append(0)
        if reciprocals:
            index["mrr"] = round(sum(reciprocals) / len(reciprocals), 4)
    return {
        "queries": summary.get("queries"),
        "index": {
            "recall_at_1": index.get("recall_at_1"),
            "recall_at_5": index.get("recall_at_5"),
            "mrr": index.get("mrr"),
            "latency_ms_avg": index.get("latency_ms_avg"),
            "latency_ms_median": index.get("latency_ms_median"),
        },
    }


def _collect_eval() -> dict[str, Any]:
    if not EVAL_JSON.exists():
        return {"available": False, "reason": f"latest eval not found at {EVAL_JSON}"}
    try:
        obj = json.loads(EVAL_JSON.read_text())
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "reason": f"could not read latest eval: {exc}"}
    # Keep private raw metrics aggregate-only too; never include eval query text/top results.
    summary = _eval_index_summary(obj)
    return {"available": True, **summary, "generated_at": obj.get("generated_at")}


def collect_metrics() -> dict[str, Any]:
    status = _collect_status()
    metrics = {
        "timestamp": _utc_now(),
        "package_version": _package_version(),
        "git_commit": _git_commit(),
        "index_db": {"path": str(DB_PATH), "size_bytes": DB_PATH.stat().st_size if DB_PATH.exists() else None},
        "status": status,
        "search_latency": _collect_search_latencies(),
        "eval": _collect_eval(),
        "environment": {
            "python_version": platform.python_version(),
            "ocrmypdf_available": shutil.which("ocrmypdf") is not None,
            "tesseract_available": shutil.which("tesseract") is not None,
            "package_install_mode": _package_install_mode(),
        },
    }
    return metrics


def _status_counts(status: dict[str, Any]) -> dict[str, int]:
    counts = status.get("counts") or {}
    return {key: int(counts.get(key, 0) or 0) for key in ["indexed", "indexed_ocr", "indexed_metadata", "skipped", "failed"]}


def _avg(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None


def build_public_summary(metrics: dict[str, Any]) -> dict[str, Any]:
    status = metrics.get("status") if isinstance(metrics.get("status"), dict) else {}
    last_run = status.get("last_run") or {}
    search = metrics.get("search_latency") if isinstance(metrics.get("search_latency"), dict) else {}
    query_rows = search.get("queries") or []
    latencies = [float(row["latency_ms"]) for row in query_rows if isinstance(row.get("latency_ms"), (int, float))]
    result_counts = [int(row["results_count"]) for row in query_rows if isinstance(row.get("results_count"), int)]
    eval_payload = metrics.get("eval") if isinstance(metrics.get("eval"), dict) else {"available": False, "reason": "not collected"}
    if eval_payload.get("summary") and not eval_payload.get("index"):
        eval_payload = {"available": eval_payload.get("available"), **_eval_index_summary(eval_payload)}

    summary = {
        "generated_at": metrics.get("timestamp"),
        "package_version": metrics.get("package_version"),
        "git_commit": metrics.get("git_commit"),
        "index_db": {
            "label": "configured local SQLite index database",
            "size_bytes": (metrics.get("index_db") or {}).get("size_bytes"),
        },
        "status_counts": _status_counts(status),
        "last_run": {
            "mode": last_run.get("mode"),
            "started_at": last_run.get("started_at"),
            "finished_at": last_run.get("finished_at"),
            "files_scanned": last_run.get("files_scanned"),
            "files_indexed": last_run.get("files_indexed"),
            "files_skipped": last_run.get("files_skipped"),
            "files_failed": last_run.get("files_failed"),
            "bytes_downloaded": last_run.get("bytes_downloaded"),
            "chunks": last_run.get("chunks"),
            "status": last_run.get("status"),
        },
        "search_latency": {
            "available": bool(search.get("available")),
            "query_set": "fixed safe generic terms; exact terms and results are not published",
            "query_count": len(query_rows),
            "avg_latency_ms": _avg(latencies),
            "median_latency_ms": round(statistics.median(latencies), 3) if latencies else None,
            "max_latency_ms": round(max(latencies), 3) if latencies else None,
            "avg_result_count": _avg(result_counts),
        },
        "eval": {
            "available": bool(eval_payload.get("available")),
            "queries": eval_payload.get("queries"),
            "index": (eval_payload.get("index") or {}) if eval_payload.get("available") else None,
            "reason": eval_payload.get("reason") if not eval_payload.get("available") else None,
        },
        "environment": {
            "python_version": (metrics.get("environment") or {}).get("python_version"),
            "ocrmypdf_available": (metrics.get("environment") or {}).get("ocrmypdf_available"),
            "tesseract_available": (metrics.get("environment") or {}).get("tesseract_available"),
            "package_install_mode": {
                "available": ((metrics.get("environment") or {}).get("package_install_mode") or {}).get("available"),
                "editable": ((metrics.get("environment") or {}).get("package_install_mode") or {}).get("editable"),
            },
        },
        "privacy": {
            "published": "aggregate counts, latencies, eval scores, and tool availability only",
            "withheld": "filenames, Google Drive paths, Drive IDs, snippets, raw eval cases, and search result documents",
        },
    }
    offenders = find_public_privacy_offenders(summary)
    if offenders:
        raise ValueError("public summary privacy guard failed: " + "; ".join(offenders))
    return summary


def find_public_privacy_offenders(obj: Any) -> list[str]:
    text = stable_json(obj)
    offenders: list[str] = []
    if PRIVATE_PATH_RE.search(text):
        offenders.append("local private path")
    if DRIVE_ID_RE.search(text):
        offenders.append("drive-like id")
    if RAW_RESULT_KEY_RE.search(text):
        offenders.append("raw result field present")
    return offenders


def _read_last_metrics(path: Path = RAW_JSONL) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        last = None
        for line in path.read_text().splitlines():
            if line.strip():
                last = line
        return json.loads(last) if last else None
    except Exception:
        return None


def alert_reasons(current: dict[str, Any], previous: dict[str, Any] | None = None) -> list[str]:
    reasons: list[str] = []
    status = current.get("status") or {}
    if not status.get("exists", False):
        reasons.append("index DB is missing or corrupt")
    last_run = status.get("last_run") or {}
    if last_run.get("status") and last_run.get("status") != "success":
        reasons.append(f"last index run status is {last_run.get('status')}")
    failed = int(last_run.get("files_failed") or 0) + int((status.get("counts") or {}).get("failed") or 0)
    if failed:
        reasons.append(f"nonzero failed file count: {failed}")
    eval_payload = current.get("eval") or {}
    if eval_payload.get("available"):
        recall5 = ((eval_payload.get("index") or {}).get("recall_at_5"))
        if isinstance(recall5, (int, float)) and recall5 < 0.85:
            reasons.append(f"eval Recall@5 below target: {recall5}")
    if previous:
        cur_summary = build_public_summary(current)
        prev_summary = build_public_summary(previous)
        cur_avg = ((cur_summary.get("search_latency") or {}).get("avg_latency_ms"))
        prev_avg = ((prev_summary.get("search_latency") or {}).get("avg_latency_ms"))
        if isinstance(cur_avg, (int, float)) and isinstance(prev_avg, (int, float)) and prev_avg > 0 and cur_avg > prev_avg * 1.75:
            reasons.append(f"search latency regression: avg {cur_avg} ms vs previous {prev_avg} ms")
        cur_r5 = (((cur_summary.get("eval") or {}).get("index") or {}).get("recall_at_5"))
        prev_r5 = (((prev_summary.get("eval") or {}).get("index") or {}).get("recall_at_5"))
        if isinstance(cur_r5, (int, float)) and isinstance(prev_r5, (int, float)) and cur_r5 < prev_r5:
            reasons.append(f"eval Recall@5 regression: {cur_r5} vs previous {prev_r5}")
    return reasons


def write_metrics(metrics: dict[str, Any], public_summary: dict[str, Any]) -> None:
    DEFAULT_METRICS_DIR.mkdir(parents=True, exist_ok=True)
    with RAW_JSONL.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(metrics, sort_keys=True, ensure_ascii=False) + "\n")
    PUBLIC_SUMMARY.write_text(stable_json(public_summary) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect real sanitized Hermes Drive Index metrics")
    parser.add_argument("--dry-run", action="store_true", help="Collect and print public summary without writing files.")
    parser.add_argument("--watchdog", action="store_true", help="Quiet mode: write metrics and print only alert state changes/regressions.")
    args = parser.parse_args(argv)

    previous = _read_last_metrics()
    metrics = collect_metrics()
    summary = build_public_summary(metrics)
    reasons = alert_reasons(metrics, previous)

    if args.dry_run:
        print(stable_json(summary))
        if reasons:
            print("\nALERT_REASONS:")
            for reason in reasons:
                print(f"- {reason}")
        return 0

    write_metrics(metrics, summary)
    if args.watchdog:
        if reasons:
            print("Hermes Drive Index metrics alert:")
            for reason in reasons:
                print(f"- {reason}")
            print(f"Public summary: {PUBLIC_SUMMARY}")
        return 0

    print(stable_json(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
