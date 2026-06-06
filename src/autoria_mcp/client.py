"""Async HTTP client for the AUTO.RIA API.

Phase 2 ships the typed exception hierarchy and the client *shape* (constructor,
async context manager) so the rest of the package can import and type against it.
The request methods are stubs that raise ``NotImplementedError`` until Phase 3.

Phase 3 responsibilities (documented here so the contract is explicit):
  * Inject ``api_key`` (and ``user_id`` for paid POSTs) as query params, never
    in logs.
  * Timeouts + retry with backoff on 429 / 5xx.
  * Local quota accounting (RIA exposes no ``X-RateLimit-*`` headers).
  * Map the two RIA error shapes to typed exceptions:
      - 4xx JSON ``{"error": {"code", "message"}}``
      - HTTP 200 with ``noticeData[].noticeType == "error"`` (POST endpoints)
"""

from __future__ import annotations

import logging
from types import TracebackType
from typing import Any

import httpx

from autoria_mcp.config import Settings

logger = logging.getLogger("autoria_mcp.client")


class AutoRiaError(Exception):
    """Base class for all client-raised errors."""


class AutoRiaConfigError(AutoRiaError):
    """Raised when a request is attempted without required configuration."""


class AutoRiaAPIError(AutoRiaError):
    """A structured error returned by the API.

    Captures both RIA error shapes behind one type.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class AutoRiaAuthError(AutoRiaAPIError):
    """Missing or invalid ``api_key`` (e.g. ``API_KEY_MISSING``/``API_KEY_INVALID``)."""


class AutoRiaRateLimitError(AutoRiaAPIError):
    """Quota exceeded (e.g. ``OVER_RATE_LIMIT`` / HTTP 429)."""


class AutoRiaClient:
    """Thin async wrapper over :class:`httpx.AsyncClient` for the AUTO.RIA API.

    Use as an async context manager so the underlying connection pool is closed::

        async with AutoRiaClient(settings) as client:
            data = await client.get_json("/auto/dictionaries/marks")
    """

    def __init__(self, settings: Settings, *, http_client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._owns_client = http_client is None
        self._http = http_client or httpx.AsyncClient(
            base_url=settings.base_url,
            timeout=httpx.Timeout(15.0, connect=5.0),
            headers={"Accept": "application/json"},
        )

    async def __aenter__(self) -> AutoRiaClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the underlying HTTP client if this instance owns it."""
        if self._owns_client:
            await self._http.aclose()

    async def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET ``path`` and return decoded JSON.

        Raises:
            NotImplementedError: until Phase 3.
        """
        # TODO(phase 3): inject api_key, retry/backoff, quota accounting,
        # error-shape mapping. Stubbed to keep the surface importable & typed.
        raise NotImplementedError("AutoRiaClient.get_json lands in Phase 3")

    async def post_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """POST ``path`` (paid endpoints) and return decoded JSON.

        Raises:
            NotImplementedError: until Phase 3.
        """
        # TODO(phase 3): inject api_key + user_id, handle noticeData error shape.
        raise NotImplementedError("AutoRiaClient.post_json lands in Phase 3")
