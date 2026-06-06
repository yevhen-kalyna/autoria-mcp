"""Logging setup for autoria-mcp.

A single ``configure_logging`` helper installs a stderr handler on the package
logger. stderr is deliberate: on the stdio transport, stdout is the MCP wire and
must not be polluted with log lines.

Never log the API key. Settings keep it in :class:`pydantic.SecretStr`, but as a
defense in depth the :class:`SecretRedactingFilter` scrubs anything that looks
like an ``api_key=`` query parameter from emitted records.
"""

from __future__ import annotations

import logging
import re
import sys

_PACKAGE_LOGGER = "autoria_mcp"

# Matches `api_key=<value>` or `user_id=<value>` in URLs/log text and replaces
# the value with `***`. Kept intentionally broad.
_SECRET_RE = re.compile(r"(?i)\b(api_key|user_id)=([^&\s\"']+)")


class SecretRedactingFilter(logging.Filter):
    """Scrub secret query params from log messages before they are emitted."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _SECRET_RE.sub(r"\1=***", record.msg)
        if record.args:
            record.args = tuple(
                _SECRET_RE.sub(r"\1=***", a) if isinstance(a, str) else a for a in record.args
            )
        return True


def configure_logging(level: str = "INFO") -> logging.Logger:
    """Configure and return the package logger.

    Idempotent: repeated calls update the level but do not stack handlers.
    """
    logger = logging.getLogger(_PACKAGE_LOGGER)
    logger.setLevel(level.upper())
    logger.propagate = False

    if not logger.handlers:
        handler = logging.StreamHandler(stream=sys.stderr)
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S%z",
            )
        )
        handler.addFilter(SecretRedactingFilter())
        logger.addHandler(handler)

    return logger
