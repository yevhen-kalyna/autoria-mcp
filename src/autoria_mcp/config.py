"""Runtime configuration for autoria-mcp.

Settings are sourced from environment variables (prefix ``AUTORIA_``) and an
optional ``.env`` file. This module is fully implemented in Phase 2 because the
server entry point and (later) the client need it to boot.

Secrets (``api_key``) are wrapped in :class:`pydantic.SecretStr` so they are not
accidentally rendered in logs or ``repr`` output. Never call ``get_secret_value``
outside the HTTP layer, and never log the result.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

Transport = Literal["stdio", "http"]
"""Public transport selector. ``http`` maps to MCP streamable-HTTP internally."""


def _default_cache_dir() -> Path:
    """Per-user cache directory, overridable via ``AUTORIA_CACHE_DIR``.

    Honors ``XDG_CACHE_HOME`` when set; otherwise falls back to ``~/.cache``.
    """
    import os

    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    return base / "autoria-mcp"


class Settings(BaseSettings):
    """Process-wide settings, loaded once from env/.env.

    Attributes:
        api_key: Personal AUTO.RIA API key, sent as the ``api_key`` query param
            on every request. Required for any real API call (Phase 3); optional
            here so the server can boot and expose the health tool without it.
        user_id: Numeric user id required by the paid POST endpoints. Optional
            until those endpoints are wired in Phase 4.
        base_url: API host. Only ``https://developers.ria.com`` is documented.
        transport: ``stdio`` (default) or ``http`` (streamable-HTTP).
        host / port: Bind address for the HTTP transport. Ignored for stdio.
        cache_dir: Root directory for the on-disk dictionary cache (Phase 3).
        cache_ttl: Default dictionary cache TTL in seconds (default 7 days).
        max_retries: Max retry attempts for retryable responses (429 / 5xx).
        backoff_base: Base delay (seconds) for exponential backoff with jitter.
        backoff_cap: Upper bound (seconds) on a single backoff sleep.
        quota_hourly_limit: Assumed hourly request quota (free pkg default 30).
        quota_monthly_limit: Assumed monthly request quota (free pkg default 1000).
        quota_warn_ratio: Log a warning once usage crosses this fraction of a
            window's limit. Accounting is warn-only; requests are never blocked.
        log_level: Root log level for the package logger.
    """

    model_config = SettingsConfigDict(
        env_prefix="AUTORIA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    api_key: SecretStr | None = Field(
        default=None,
        description="AUTO.RIA API key (query param `api_key`). Never logged.",
    )
    user_id: str | None = Field(
        default=None,
        description="User id (query param `user_id`) for paid POST endpoints.",
    )
    base_url: str = Field(
        default="https://developers.ria.com",
        description="API base URL; only the production host is documented.",
    )
    transport: Transport = Field(
        default="stdio",
        description="MCP transport: 'stdio' or 'http' (streamable-HTTP).",
    )
    host: str = Field(default="127.0.0.1", description="HTTP transport bind host.")
    port: int = Field(default=8000, ge=1, le=65535, description="HTTP transport port.")
    cache_dir: Path = Field(
        default_factory=_default_cache_dir,
        description="On-disk cache root for dictionaries (Phase 3).",
    )
    cache_ttl: int = Field(
        default=7 * 24 * 60 * 60,
        ge=0,
        description="Default dictionary cache TTL in seconds.",
    )
    max_retries: int = Field(
        default=3,
        ge=0,
        description="Max retry attempts for retryable responses (429 / 5xx).",
    )
    backoff_base: float = Field(
        default=0.5,
        gt=0,
        description="Base delay (seconds) for exponential backoff with full jitter.",
    )
    backoff_cap: float = Field(
        default=8.0,
        gt=0,
        description="Upper bound (seconds) on a single backoff sleep.",
    )
    quota_hourly_limit: int = Field(
        default=30,
        ge=0,
        description="Assumed hourly request quota (free package default).",
    )
    quota_monthly_limit: int = Field(
        default=1000,
        ge=0,
        description="Assumed monthly request quota (free package default).",
    )
    quota_warn_ratio: float = Field(
        default=0.9,
        gt=0,
        le=1,
        description="Warn once usage crosses this fraction of a window limit.",
    )
    log_level: str = Field(default="INFO", description="Package log level.")

    @property
    def has_credentials(self) -> bool:
        """True when an API key is configured (does not validate it)."""
        return self.api_key is not None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return process-wide settings, constructed once and cached.

    Tests that need a fresh load (e.g. after mutating ``os.environ``) should call
    ``get_settings.cache_clear()`` first.
    """
    return Settings()
