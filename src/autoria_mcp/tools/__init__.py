"""FastMCP tool registry for autoria-mcp.

Phase 2 registers only the health/``ping`` tool. Phases 3-4 add the curated
high-level tools (``search_used_cars``, ``get_car_details``, ``get_average_price``,
``lookup_brands``/``lookup_models``/``lookup_regions``) plus thin mirrors of the
long-tail endpoints, each registered from its own module here.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from autoria_mcp.tools.health import register_health_tools


def register_all(mcp: FastMCP) -> None:
    """Register every tool module on the given FastMCP app."""
    register_health_tools(mcp)
    # TODO(phase 4): register_search_tools(mcp), register_lookup_tools(mcp), ...


__all__ = ["register_all"]
