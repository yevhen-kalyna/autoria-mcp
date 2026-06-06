"""FastMCP application wiring and process entry point.

Builds the ``autoria`` MCP server, registers tools, selects the transport
(stdio by default, streamable-HTTP behind ``--transport http`` /
``AUTORIA_TRANSPORT=http``), and exposes ``main()`` for the console script.

Transport is intentionally not hardcoded: the public selector lives in
:class:`autoria_mcp.config.Settings` and maps ``http`` -> MCP ``streamable-http``.
"""

from __future__ import annotations

import argparse
import os
from typing import Literal, cast

from mcp.server.fastmcp import FastMCP

from autoria_mcp import __version__
from autoria_mcp.config import Settings, Transport, get_settings
from autoria_mcp.logging_config import configure_logging
from autoria_mcp.tools import register_all

# Public transport values exposed on the CLI / via AUTORIA_TRANSPORT.
_TRANSPORT_CHOICES: tuple[Transport, ...] = ("stdio", "http")

# MCP SDK transport literals we actually run on.
_McpTransport = Literal["stdio", "streamable-http"]
_LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
_LOG_LEVELS: frozenset[str] = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


def _mcp_transport(transport: Transport) -> _McpTransport:
    """Map the public transport selector to the MCP SDK transport literal."""
    return "stdio" if transport == "stdio" else "streamable-http"


def _log_level_literal(level: str) -> _LogLevel:
    """Coerce a free-form level string to the Literal FastMCP expects."""
    upper = level.upper()
    if upper in _LOG_LEVELS:
        return cast(_LogLevel, upper)
    return "INFO"


def build_server(settings: Settings) -> FastMCP:
    """Construct the FastMCP app and register all tools.

    Kept separate from :func:`main` so tests can build and introspect the server
    without starting an event loop or a transport.
    """
    mcp = FastMCP(
        "autoria",
        instructions=(
            "Agent-friendly access to the AUTO.RIA used-car market (auto.ria.com). "
            "Resolve brand/model/region names to IDs via the lookup tools, then "
            "search. API quota is scarce - prefer cached lookups and narrow filters."
        ),
        host=settings.host,
        port=settings.port,
        log_level=_log_level_literal(settings.log_level),
    )
    register_all(mcp)
    return mcp


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="autoria-mcp",
        description="MCP server for the AUTO.RIA used-cars API.",
    )
    parser.add_argument("--version", action="version", version=f"autoria-mcp {__version__}")
    parser.add_argument(
        "--transport",
        choices=_TRANSPORT_CHOICES,
        default=None,
        help="Transport to serve on (overrides AUTORIA_TRANSPORT). Default: stdio.",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="Bind host for the HTTP transport (overrides AUTORIA_HOST).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Bind port for the HTTP transport (overrides AUTORIA_PORT).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Console entry point: parse args, load settings, run the chosen transport."""
    args = _parse_args(argv)

    # CLI flags win over env. We push them into the environment *before* loading
    # settings so there is a single source of truth and the `ping` tool reports
    # the effective transport.
    if args.transport is not None:
        os.environ["AUTORIA_TRANSPORT"] = args.transport
    if args.host is not None:
        os.environ["AUTORIA_HOST"] = args.host
    if args.port is not None:
        os.environ["AUTORIA_PORT"] = str(args.port)

    get_settings.cache_clear()
    settings = get_settings()

    logger = configure_logging(settings.log_level)
    logger.info(
        "starting autoria-mcp %s (transport=%s, base_url=%s, credentials=%s)",
        __version__,
        settings.transport,
        settings.base_url,
        "yes" if settings.has_credentials else "no",
    )

    mcp = build_server(settings)
    mcp.run(transport=_mcp_transport(settings.transport))


if __name__ == "__main__":  # pragma: no cover
    main()
