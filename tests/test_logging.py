"""SecretRedactingFilter scrubs api_key/user_id from log output."""

from __future__ import annotations

import logging

from autoria_mcp.logging_config import SecretRedactingFilter


def _record(msg: str, *args: object) -> logging.LogRecord:
    return logging.LogRecord(
        name="autoria_mcp.client",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=args,
        exc_info=None,
    )


def test_redacts_secrets_in_message() -> None:
    record = _record("GET /auto/colors?api_key=abc123&user_id=777&marka_id=9")
    assert SecretRedactingFilter().filter(record) is True
    assert "abc123" not in record.msg
    assert "777" not in record.msg
    assert "api_key=***" in record.msg
    assert "user_id=***" in record.msg
    assert "marka_id=9" in record.msg  # non-secret params survive


def test_redacts_secrets_in_args() -> None:
    record = _record("request %s", "url?api_key=topsecret&user_id=42")
    SecretRedactingFilter().filter(record)
    rendered = record.getMessage()
    assert "topsecret" not in rendered
    assert "42" not in rendered
    assert "api_key=***" in rendered
