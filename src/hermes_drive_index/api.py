"""Public API.

Each entry point accepts an optional ``cfg`` (a resolved ``DriveIndexConfig``).
When omitted, ``default_config()`` is used, preserving the zero-argument
signatures the Hermes adapter relies on.
"""

from __future__ import annotations

from pathlib import Path

from .config import DriveIndexConfig, default_config
from .core.benchmark import benchmark_ocr_parameters as _benchmark_ocr_parameters
from .core.manifest import plan_incremental_actions
from .core.models import DriveFile
from .core.orchestrator import build_index as _build_index
from .core.orchestrator import incremental_update as _incremental_update
from .core.orchestrator import reindex_metadata_only as _reindex_metadata_only
from .core.orchestrator import search as _search
from .core.orchestrator import status as _status


def build_index(cfg: DriveIndexConfig | None = None) -> dict:
    return _build_index(cfg or default_config())


def incremental_update(cfg: DriveIndexConfig | None = None) -> dict:
    return _incremental_update(cfg or default_config())


def reindex_metadata_only(cfg: DriveIndexConfig | None = None) -> dict:
    return _reindex_metadata_only(cfg or default_config())


def benchmark_ocr_parameters(
    cfg: DriveIndexConfig | None = None,
    *,
    modes: list[str] | None = None,
    limit: int | None = None,
    golden_path: str | Path | None = None,
) -> dict:
    return _benchmark_ocr_parameters(
        cfg or default_config(),
        modes=modes,
        limit=limit,
        golden_path=Path(golden_path).expanduser() if golden_path else None,
    )


def search(query: str, top_k: int = 8, cfg: DriveIndexConfig | None = None) -> dict:
    return _search(cfg or default_config(), query=query, top_k=top_k)


def status(cfg: DriveIndexConfig | None = None) -> dict:
    return _status(cfg or default_config())


__all__ = ["DriveFile", "plan_incremental_actions", "build_index", "incremental_update", "reindex_metadata_only", "benchmark_ocr_parameters", "search", "status"]
