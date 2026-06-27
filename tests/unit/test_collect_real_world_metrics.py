"""Tests for sanitized real-world metrics collection helpers."""

from __future__ import annotations

import importlib.util
import pathlib


SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "collect_real_world_metrics.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("collect_real_world_metrics", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_public_summary_contains_only_aggregate_search_and_eval_metrics():
    collector = _load_module()
    private_metrics = {
        "timestamp": "2026-06-26T00:00:00+00:00",
        "package_version": "0.1.0",
        "git_commit": "abcdef1",
        "index_db": {"path": "/".join(["", "home", "gregory", ".hermes", "drive_index", "personal_files", "index.db"]), "size_bytes": 1234},
        "status": {
            "exists": True,
            "counts": {"indexed": 2, "indexed_ocr": 1, "indexed_metadata": 1, "skipped": 3},
            "last_run": {
                "mode": "incremental_manifest",
                "started_at": "2026-06-26T00:00:00+00:00",
                "finished_at": "2026-06-26T00:00:01+00:00",
                "files_scanned": 7,
                "files_indexed": 2,
                "files_skipped": 3,
                "files_failed": 0,
                "bytes_downloaded": 0,
                "chunks": 4,
                "status": "success",
            },
        },
        "search_latency": {
            "available": True,
            "queries": [
                {"label": "generic_0", "query": "receipt", "latency_ms": 1.2, "results_count": 2, "top_name": "Private Receipt.pdf", "snippet": "personal snippet"},
                {"label": "generic_1", "query": "policy", "latency_ms": 2.8, "results_count": 1, "top_name": "Policy Gregory.pdf"},
            ],
        },
        "eval": {
            "available": True,
            "summary": {
                "queries": 5,
                "index": {"recall_at_1": 0.8, "recall_at_5": 1.0, "mrr": 0.9, "latency_ms_avg": 37.2},
            },
            "results": [{"query": "Gregory private", "top_results": ["Private.pdf"]}],
        },
        "environment": {"python_version": "3.11.0", "ocrmypdf_available": False, "tesseract_available": True},
    }

    summary = collector.build_public_summary(private_metrics)
    text = collector.stable_json(summary)

    assert summary["status_counts"] == {"indexed": 2, "indexed_ocr": 1, "indexed_metadata": 1, "skipped": 3, "failed": 0}
    assert summary["search_latency"]["query_count"] == 2
    assert summary["search_latency"]["avg_latency_ms"] == 2.0
    assert summary["eval"]["index"]["recall_at_5"] == 1.0
    assert "Private Receipt" not in text
    assert "Gregory" not in text
    assert "personal snippet" not in text
    assert "/home/gregory" not in text


def test_public_summary_privacy_guard_flags_drive_ids_paths_and_snippets():
    collector = _load_module()
    bad_path = "/".join(["", "home", "gregory", ".hermes", "drive_index", "personal_files", "index.db"])
    summary = {"note": f"bad {bad_path} and drive id 1AbCdEfGhIjKlMnOpQrStUvWxYz123456"}

    offenders = collector.find_public_privacy_offenders(summary)

    assert offenders
    assert any("local private path" in item or "drive-like id" in item for item in offenders)
