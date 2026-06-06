"""Async HTTP client for the AUTO.RIA API.

The client injects credentials, retries transient failures, accounts for the
scarce API quota locally, and maps RIA's two error shapes onto a typed exception
hierarchy. It is the single I/O chokepoint every curated tool will build on.

Two RIA error shapes, both handled here:
  * 4xx JSON ``{"error": {"code", "message"}}`` (also a flat ``{"message": ...}``
    on some 404s) -> mapped by ``code``/status to the typed exceptions below.
  * HTTP 200 with ``noticeData[].noticeType == "error"`` (POST endpoints) ->
    inspected on success and raised even though the status is 200.

Secrets (``api_key``, ``user_id``) are sourced from :class:`Settings`, injected
as query params, and never logged: the request log line carries only the
secret-free params, and :mod:`autoria_mcp.logging_config` redacts as defense in
depth.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from types import TracebackType
from typing import Any

import httpx

from autoria_mcp.config import Settings
from autoria_mcp.quota import QuotaTracker

logger = logging.getLogger("autoria_mcp.client")

# Error codes (4xx body) that mean the key itself is the problem.
_AUTH_CODES = frozenset(
    {
        "API_KEY_MISSING",
        "API_KEY_INVALID",
        "API_KEY_DISABLED",
        "API_KEY_UNAUTHORIZED",
        "API_KEY_UNVERIFIED",
    }
)
_RATE_LIMIT_CODE = "OVER_RATE_LIMIT"
_SECRET_PARAMS = frozenset({"api_key", "user_id"})


class AutoRiaError(Exception):
    """Base class for all client-raised errors."""


class AutoRiaConfigError(AutoRiaError):
    """Raised when a request is attempted without required configuration."""


class AutoRiaLookupError(AutoRiaError):
    """Raised when a dictionary name cannot be resolved to an id.

    Carries the nearest candidates so an agent can recover without guessing.
    """


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


def _safe_params(params: dict[str, Any]) -> dict[str, Any]:
    """Return ``params`` without secret keys, for logging."""
    return {k: v for k, v in params.items() if k not in _SECRET_PARAMS}


class AutoRiaClient:
    """Thin async wrapper over :class:`httpx.AsyncClient` for the AUTO.RIA API.

    Use as an async context manager so the underlying connection pool is closed::

        async with AutoRiaClient(settings) as client:
            data = await client.get_json("/auto/categories/1/marks")
    """

    def __init__(
        self,
        settings: Settings,
        *,
        http_client: httpx.AsyncClient | None = None,
        quota: QuotaTracker | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self._settings = settings
        self._owns_client = http_client is None
        self._http = http_client or httpx.AsyncClient(
            base_url=settings.base_url,
            timeout=httpx.Timeout(15.0, connect=5.0),
            headers={"Accept": "application/json"},
        )
        self._quota = quota or QuotaTracker(
            settings.cache_dir / "quota.json",
            hourly_limit=settings.quota_hourly_limit,
            monthly_limit=settings.quota_monthly_limit,
            warn_ratio=settings.quota_warn_ratio,
        )
        # Injectable so tests can run retries without real delays.
        self._sleep: Callable[[float], Awaitable[None]] = sleep or asyncio.sleep

    @property
    def settings(self) -> Settings:
        """Read-only access to the settings this client was built with."""
        return self._settings

    @property
    def quota(self) -> QuotaTracker:
        """The local quota tracker (usage is warn-only; requests never blocked)."""
        return self._quota

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
        """GET ``path`` and return decoded JSON. Injects ``api_key``."""
        return await self._request("GET", path, params, needs_user_id=False)

    async def post_json(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        json_body: Any = None,
    ) -> Any:
        """POST ``path`` (paid endpoints) and return decoded JSON.

        ``api_key`` and ``user_id`` are injected as query params (per the API);
        ``json_body``, when given, is sent as the ``application/json`` request
        body (httpx sets the ``Content-Type`` header automatically). Raises on
        the HTTP-200 ``noticeData`` error shape these endpoints use.
        """
        return await self._request("POST", path, params, needs_user_id=True, json_body=json_body)

    # -- internals -----------------------------------------------------------

    def _build_query(self, params: dict[str, Any] | None, *, needs_user_id: bool) -> dict[str, Any]:
        """Merge caller params with injected credentials, or raise if missing."""
        query: dict[str, Any] = dict(params or {})
        api_key = self._settings.api_key
        if api_key is None:
            raise AutoRiaConfigError(
                "AUTORIA_API_KEY is not set. Get a key at https://developers.ria.com "
                "and export it before making API calls."
            )
        query["api_key"] = api_key.get_secret_value()
        if needs_user_id:
            user_id = self._settings.user_id
            if not user_id:
                raise AutoRiaConfigError(
                    "AUTORIA_USER_ID is required for paid POST endpoints but is not set."
                )
            query["user_id"] = user_id
        return query

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None,
        *,
        needs_user_id: bool,
        json_body: Any = None,
    ) -> Any:
        query = self._build_query(params, needs_user_id=needs_user_id)
        attempts = self._settings.max_retries + 1

        for attempt in range(attempts):
            logger.debug("%s %s params=%s", method, path, _safe_params(query))
            response = await self._http.request(method, path, params=query, json=json_body)
            status = response.status_code

            if status < 400:
                # Accounting must never break an otherwise-successful call.
                try:
                    await self._quota.record()
                except Exception:  # quota tracking is best-effort, never fatal
                    logger.debug("quota accounting failed for %s", path)
                data = self._decode(response)
                self._raise_for_notice(data)
                return data

            if self._is_retryable(status) and attempt < attempts - 1:
                delay = self._backoff_delay(attempt)
                logger.debug(
                    "retryable %s on %s (attempt %d/%d); backing off %.2fs",
                    status,
                    path,
                    attempt + 1,
                    attempts,
                    delay,
                )
                await self._sleep(delay)
                continue

            raise self._error_for_response(response)

        # Loop always returns or raises; this satisfies the type checker.
        raise AutoRiaAPIError("request failed after retries", status_code=None)

    @staticmethod
    def _is_retryable(status: int) -> bool:
        return status == 429 or 500 <= status < 600

    def _backoff_delay(self, attempt: int) -> float:
        """Exponential backoff with full jitter, capped at ``backoff_cap``."""
        ceiling: float = min(
            self._settings.backoff_cap,
            self._settings.backoff_base * (2**attempt),
        )
        return random.random() * ceiling

    @staticmethod
    def _decode(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            raise AutoRiaAPIError(
                "AUTO.RIA returned a non-JSON response",
                status_code=response.status_code,
            ) from exc

    @staticmethod
    def _raise_for_notice(data: Any) -> None:
        """Raise on the HTTP-200 ``noticeData[].noticeType == 'error'`` shape."""
        if not isinstance(data, dict):
            return
        notices = data.get("noticeData")
        if not isinstance(notices, list):
            return
        messages = [
            str(n.get("noticeString") or n.get("message") or "unspecified error")
            for n in notices
            if isinstance(n, dict) and n.get("noticeType") == "error"
        ]
        if messages:
            raise AutoRiaAPIError(
                "; ".join(messages),
                code="NOTICE_ERROR",
                status_code=200,
            )

    def _error_for_response(self, response: httpx.Response) -> AutoRiaAPIError:
        """Map a >=400 response (either body shape) to a typed exception."""
        status = response.status_code
        code: str | None = None
        message: str | None = None
        try:
            body = response.json()
        except ValueError:
            body = None

        if isinstance(body, dict):
            err = body.get("error")
            if isinstance(err, dict):
                code = err.get("code")
                message = err.get("message")
            elif isinstance(body.get("message"), str):
                message = body["message"]

        message = message or f"AUTO.RIA request failed with HTTP {status}"

        if code in _AUTH_CODES:
            return AutoRiaAuthError(message, code=code, status_code=status)
        if code == _RATE_LIMIT_CODE or status == 429:
            return AutoRiaRateLimitError(
                message,
                code=code or _RATE_LIMIT_CODE,
                status_code=status,
            )
        return AutoRiaAPIError(message, code=code, status_code=status)
