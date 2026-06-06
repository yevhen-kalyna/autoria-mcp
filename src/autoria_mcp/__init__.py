"""autoria-mcp: an MCP server exposing the AUTO.RIA used-cars REST API to agents.

The public surface intentionally stays small in Phase 2 (scaffold). Concrete
client, cache, dictionary-resolution, and tool implementations land in
Phases 3-4.
"""

from __future__ import annotations

from importlib import metadata

try:
    __version__ = metadata.version("autoria-mcp")
except metadata.PackageNotFoundError:  # pragma: no cover - editable/source checkout
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
