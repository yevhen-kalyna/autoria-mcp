"""Health/diagnostic tools.

``ping`` is a zero-quota, no-network tool that lets an agent (or a smoke test)
confirm the server is up and inspect basic configuration without touching the
AUTO.RIA API. It never returns the API key — only whether one is configured.
"""

from __future__ import annotations

from typing import Annotated, TypedDict

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from autoria_mcp import __version__
from autoria_mcp.config import get_settings


class PingResult(TypedDict):
    """Structured result of the ``ping`` tool."""

    status: str
    server: str
    version: str
    transport: str
    credentials_configured: bool


def register_health_tools(mcp: FastMCP) -> None:
    """Register health tools on ``mcp``."""

    @mcp.tool()
    def ping(
        echo: Annotated[
            str | None,
            Field(default=None, description="Optional string echoed back in the result."),
        ] = None,
    ) -> PingResult:
        """Liveness check for the autoria MCP server.

        Returns server name, package version, the active transport, and whether
        an API key is configured. Costs zero API quota and makes no network call.
        Use it to verify wiring before invoking real tools.
        """
        settings = get_settings()
        result: PingResult = {
            "status": "ok" if echo is None else f"ok: {echo}",
            "server": "autoria",
            "version": __version__,
            "transport": settings.transport,
            "credentials_configured": settings.has_credentials,
        }
        return result
