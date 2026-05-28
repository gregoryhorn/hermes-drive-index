"""Public API."""

from __future__ import annotations

from .config import default_config
from .core.manifest import plan_incremental_actions
from .core.models import DriveFile
from .core.orchestrator import build_index as _build_index
from .core.orchestrator import incremental_update as _incremental_update
from .core.orchestrator import search as _search
from .core.orchestrator import status as _status


def build_index() -> dict:
    return _build_index(default_config())


def incremental_update() -> dict:
    return _incremental_update(default_config())


def search(query: str, top_k: int = 8) -> dict:
    return _search(default_config(), query=query, top_k=top_k)


def status() -> dict:
    return _status(default_config())


__all__ = ["DriveFile", "plan_incremental_actions", "build_index", "incremental_update", "search", "status"]
