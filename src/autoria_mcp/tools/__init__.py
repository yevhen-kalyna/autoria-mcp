"""FastMCP tool registry for autoria-mcp.

Each tool/resource group lives in its own module and exposes a ``register_*``
function; :func:`register_all` wires them onto the FastMCP app. ``ping`` is
registered first (it needs no runtime); the curated, paid, mirror, and resource
groups follow.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from autoria_mcp.tools.details import register_details_tools
from autoria_mcp.tools.health import register_health_tools
from autoria_mcp.tools.lookups import register_lookup_tools
from autoria_mcp.tools.mirrors import register_mirror_tools
from autoria_mcp.tools.paid import register_paid_tools
from autoria_mcp.tools.resources import register_resources
from autoria_mcp.tools.search import register_search_tools


def register_all(mcp: FastMCP) -> None:
    """Register every tool module and resource group on the given FastMCP app."""
    register_health_tools(mcp)
    register_lookup_tools(mcp)
    register_search_tools(mcp)
    register_details_tools(mcp)
    register_paid_tools(mcp)
    register_mirror_tools(mcp)
    register_resources(mcp)


__all__ = ["register_all"]
