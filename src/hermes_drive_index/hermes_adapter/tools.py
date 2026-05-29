"""Thin Hermes tool wrappers.

Handlers are deliberately stateless: they parse args, call package API functions,
and return JSON strings. This avoids long-lived wrapper defaults drifting from the
core implementation.

Adapter contract (stable, relied on by Hermes):

* Every handler returns a JSON **string** with a top-level ``success`` bool and a
  ``package_version`` field, on both the success and error paths. Errors never
  raise out of the handler — they are reported as ``{"success": false, "error": ...}``.
* ``check_drive_index_requirements`` intentionally returns ``True`` so the tools
  stay discoverable; any real failure surfaces as a structured error at call time.
* ``drive_index_search`` clamps ``top_k`` to the range 1–25.
* ``drive_index_update`` is long-running and is the same code path the CLI uses,
  so it is safe to drive from a cron wrapper (``hermes-drive-index update``).
"""

from __future__ import annotations

import json
from typing import Any

from hermes_drive_index import __version__
from hermes_drive_index.api import build_index, incremental_update, reindex_metadata_only, search, status


def check_drive_index_requirements() -> bool:
    try:
        status()
        return True
    except Exception:
        # Keep available if package imports; individual handlers return structured errors.
        return True


def drive_index_search(query: str, top_k: int = 8) -> str:
    if not query or not query.strip():
        return json.dumps({"success": False, "error": "query is required"})
    try:
        result = search(query=query, top_k=max(1, min(int(top_k or 8), 25)))
        return json.dumps({"success": True, "package_version": __version__, **result}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"success": False, "error": repr(exc), "package_version": __version__}, ensure_ascii=False)


def drive_index_status() -> str:
    try:
        result = status()
        return json.dumps({"success": True, "package_version": __version__, **result}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"success": False, "error": repr(exc), "package_version": __version__}, ensure_ascii=False)


def drive_index_update(mode: str = "incremental_manifest") -> str:
    try:
        normalized = (mode or "incremental_manifest").strip().lower()
        if normalized in {"incremental", "incremental_manifest"}:
            result = incremental_update()
        elif normalized == "reindex_metadata_only":
            result = reindex_metadata_only()
        else:
            result = build_index()
        result["requested_mode"] = mode
        return json.dumps({"success": True, "package_version": __version__, **result}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"success": False, "error": repr(exc), "requested_mode": mode, "package_version": __version__}, ensure_ascii=False)


DRIVE_INDEX_SEARCH_SCHEMA: dict[str, Any] = {
    "name": "drive_index_search",
    "description": "Search the configured local Google Drive document index. Returns ranked snippets and Drive links.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query."},
            "top_k": {"type": "integer", "description": "Maximum results, 1-25. Default 8.", "default": 8},
        },
        "required": ["query"],
    },
}

DRIVE_INDEX_STATUS_SCHEMA: dict[str, Any] = {
    "name": "drive_index_status",
    "description": "Check whether the configured local Google Drive index exists and view last run metrics.",
    "parameters": {"type": "object", "properties": {}, "required": []},
}

DRIVE_INDEX_UPDATE_SCHEMA: dict[str, Any] = {
    "name": "drive_index_update",
    "description": "Update the configured local Google Drive document index. Incremental manifest mode is the safe default.",
    "parameters": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "description": "Update mode: incremental/incremental_manifest, reindex_metadata_only, or weekly_full/full.", "default": "incremental_manifest"}
        },
        "required": [],
    },
}


#: Single source of truth for the registered tools. Both Hermes entry points
#: (``register(ctx)`` and ``register_tools(registry)``) iterate this list, so the
#: two code paths cannot drift. Keep names and schemas byte-stable.
TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "drive_index_search",
        "toolset": "drive_index",
        "schema": DRIVE_INDEX_SEARCH_SCHEMA,
        "handler": lambda args, **kw: drive_index_search(query=args.get("query", ""), top_k=args.get("top_k", 8)),
        "check_fn": check_drive_index_requirements,
        "emoji": "🗂️",
    },
    {
        "name": "drive_index_status",
        "toolset": "drive_index",
        "schema": DRIVE_INDEX_STATUS_SCHEMA,
        "handler": lambda args, **kw: drive_index_status(),
        "check_fn": check_drive_index_requirements,
        "emoji": "🗂️",
    },
    {
        "name": "drive_index_update",
        "toolset": "drive_index",
        "schema": DRIVE_INDEX_UPDATE_SCHEMA,
        "handler": lambda args, **kw: drive_index_update(mode=args.get("mode", "incremental_manifest")),
        "check_fn": check_drive_index_requirements,
        "emoji": "🗂️",
        "max_result_size_chars": 20000,
    },
]


def plugin_context_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Return the subset accepted by Hermes ``PluginContext.register_tool``.

    The legacy registry path accepts adapter-only metadata such as
    ``max_result_size_chars``. The pip-plugin ``PluginContext`` path historically
    received only the core registration fields, so keep that compatibility while
    still deriving both paths from the same ``TOOL_SPECS`` list.
    """
    return {key: spec[key] for key in ("name", "toolset", "schema", "handler", "check_fn", "emoji")}


def register_tools(registry, **_: Any) -> None:
    for spec in TOOL_SPECS:
        registry.register(**spec)
