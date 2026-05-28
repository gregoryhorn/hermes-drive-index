"""Hermes plugin adapter for hermes-drive-index."""

from __future__ import annotations

from .tools import TOOL_SPECS, plugin_context_spec, register_tools


def register(ctx) -> None:
    """Hermes plugin entry point.

    Hermes pip plugins are loaded as modules and called with a PluginContext.
    Keep this adapter thin and delegate all behavior to stateless wrappers.
    Tool definitions live in ``tools.TOOL_SPECS`` so this entry point and
    ``register_tools`` cannot drift.
    """
    for spec in TOOL_SPECS:
        ctx.register_tool(**plugin_context_spec(spec))


__all__ = ["register", "register_tools", "TOOL_SPECS"]
