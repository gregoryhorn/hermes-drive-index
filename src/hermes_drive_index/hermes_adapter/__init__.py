"""Hermes plugin adapter for hermes-drive-index."""

from __future__ import annotations

from .tools import (
    DRIVE_INDEX_SEARCH_SCHEMA,
    DRIVE_INDEX_STATUS_SCHEMA,
    DRIVE_INDEX_UPDATE_SCHEMA,
    check_drive_index_requirements,
    drive_index_search,
    drive_index_status,
    drive_index_update,
    register_tools,
)


def register(ctx) -> None:
    """Hermes plugin entry point.

    Hermes pip plugins are loaded as modules and called with a PluginContext.
    Keep this adapter thin and delegate all behavior to stateless wrappers.
    """
    ctx.register_tool(
        name="drive_index_search",
        toolset="drive_index",
        schema=DRIVE_INDEX_SEARCH_SCHEMA,
        handler=lambda args, **kw: drive_index_search(query=args.get("query", ""), top_k=args.get("top_k", 8)),
        check_fn=check_drive_index_requirements,
        emoji="🗂️",
    )
    ctx.register_tool(
        name="drive_index_status",
        toolset="drive_index",
        schema=DRIVE_INDEX_STATUS_SCHEMA,
        handler=lambda args, **kw: drive_index_status(),
        check_fn=check_drive_index_requirements,
        emoji="🗂️",
    )
    ctx.register_tool(
        name="drive_index_update",
        toolset="drive_index",
        schema=DRIVE_INDEX_UPDATE_SCHEMA,
        handler=lambda args, **kw: drive_index_update(mode=args.get("mode", "incremental_manifest")),
        check_fn=check_drive_index_requirements,
        emoji="🗂️",
    )


__all__ = ["register", "register_tools"]
