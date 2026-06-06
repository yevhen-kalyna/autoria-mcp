"""Phase 2 smoke tests: package imports, settings load from env, ping registered.

These run with zero network and zero API quota.
"""

from __future__ import annotations

import pytest

import autoria_mcp
from autoria_mcp.config import Settings, get_settings
from autoria_mcp.server import build_server


def test_package_imports_and_exposes_version() -> None:
    assert isinstance(autoria_mcp.__version__, str)
    assert autoria_mcp.__version__


def test_settings_defaults() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.base_url == "https://developers.ria.com"
    assert settings.transport == "stdio"
    assert settings.has_credentials is False


def test_settings_load_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTORIA_API_KEY", "secret-key-value")
    monkeypatch.setenv("AUTORIA_USER_ID", "12345")
    monkeypatch.setenv("AUTORIA_TRANSPORT", "http")
    monkeypatch.setenv("AUTORIA_PORT", "9001")
    get_settings.cache_clear()

    settings = get_settings()
    try:
        assert settings.transport == "http"
        assert settings.user_id == "12345"
        assert settings.port == 9001
        assert settings.has_credentials is True
        # Secret must not leak through repr/str.
        assert "secret-key-value" not in repr(settings)
        assert settings.api_key is not None
        assert settings.api_key.get_secret_value() == "secret-key-value"
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_ping_tool_registered() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    mcp = build_server(settings)
    tools = await mcp.list_tools()
    names = {tool.name for tool in tools}
    assert "ping" in names
