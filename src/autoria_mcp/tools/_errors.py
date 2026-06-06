"""Map the client's typed exceptions onto clean MCP tool errors.

Every curated/paid/mirror tool wraps its body in :func:`tool_errors`, so the
whole typed hierarchy (missing credentials, quota/429, 4xx API errors, the
HTTP-200 notice-error shape, and name-lookup failures) surfaces to the agent as
a single, actionable ``ToolError`` instead of an opaque traceback.

The client builds its exception messages without secrets (the ``api_key`` and
``user_id`` are query-only and excluded from every message), so passing the
message straight through never leaks a credential.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server.fastmcp.exceptions import ToolError

from autoria_mcp.client import AutoRiaError


@asynccontextmanager
async def tool_errors() -> AsyncIterator[None]:
    """Re-raise any :class:`AutoRiaError` as a :class:`ToolError`."""
    try:
        yield
    except AutoRiaError as exc:
        raise ToolError(str(exc)) from exc
