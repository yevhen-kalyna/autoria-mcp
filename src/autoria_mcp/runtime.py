"""Shared async runtime for the MCP tools.

Every real tool needs the same dependencies: the HTTP client, the dictionary
resolver, and the two caches (7-day dictionaries vs. short-lived volatile
search/stats). Rather than thread those through every tool signature, they are
bundled into a frozen :class:`RuntimeContext` that a FastMCP ``lifespan`` builds
once at startup and tears down at shutdown, and that tools reach through the
module-level :func:`get_runtime` provider.

Why a module singleton *and* a lifespan: the lifespan owns the lifecycle (it is
the only writer — ``set`` on enter, ``reset`` + ``client.aclose()`` on exit),
while the provider gives tool *and resource* wrappers one uniform, ``Context``-free
access pattern. This assumes a single runtime per process, which holds for stdio
and a single streamable-HTTP app. A future multi-tenant mode should instead read
``ctx.request_context.lifespan_context`` per request.

Tests do not need any of this: they build a :class:`RuntimeContext` by hand with
a respx-mocked client and call the ``*_impl`` service functions directly.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass

from mcp.server.fastmcp import FastMCP

from autoria_mcp.cache import Cache, MemoryCache, TwoTierCache
from autoria_mcp.client import AutoRiaClient
from autoria_mcp.config import Settings
from autoria_mcp.dictionaries import DictionaryResolver


@dataclass(frozen=True)
class RuntimeContext:
    """The shared dependencies every curated/paid/mirror tool builds on."""

    settings: Settings
    client: AutoRiaClient
    resolver: DictionaryResolver
    dict_cache: Cache
    volatile_cache: Cache


def build_runtime(settings: Settings) -> RuntimeContext:
    """Construct a fully-wired :class:`RuntimeContext` from ``settings``.

    The dictionary cache is the durable two-tier store (long TTL, bounded LRU
    memory tier); the volatile cache is a bounded, memory-only LRU for the
    fast-changing search/statistics responses.
    """
    dict_cache = TwoTierCache(
        settings.cache_dir,
        max_memory_entries=settings.memory_cache_max,
    )
    volatile_cache = MemoryCache(settings.memory_cache_max)
    client = AutoRiaClient(settings)
    resolver = DictionaryResolver(client, dict_cache)
    return RuntimeContext(
        settings=settings,
        client=client,
        resolver=resolver,
        dict_cache=dict_cache,
        volatile_cache=volatile_cache,
    )


_runtime: RuntimeContext | None = None


def set_runtime(runtime: RuntimeContext) -> None:
    """Install the process-wide runtime (called by the lifespan)."""
    global _runtime
    _runtime = runtime


def reset_runtime() -> None:
    """Clear the process-wide runtime (called on lifespan exit / by tests)."""
    global _runtime
    _runtime = None


def get_runtime() -> RuntimeContext:
    """Return the active runtime, or raise if the server is not running.

    Tools call this; it is set for the duration of the FastMCP lifespan.
    """
    if _runtime is None:
        raise RuntimeError(
            "autoria-mcp runtime is not initialized; tools may only run inside a "
            "started server (the FastMCP lifespan installs the runtime)."
        )
    return _runtime


def make_runtime_lifespan(
    settings: Settings,
) -> Callable[[FastMCP], AbstractAsyncContextManager[RuntimeContext]]:
    """Build a FastMCP ``lifespan`` that owns the runtime for ``settings``.

    Closing over ``settings`` (rather than re-reading globals) keeps the
    ``Settings`` passed to ``build_server`` authoritative for the whole run.
    """

    @asynccontextmanager
    async def lifespan(_server: FastMCP) -> AsyncIterator[RuntimeContext]:
        runtime = build_runtime(settings)
        set_runtime(runtime)
        try:
            yield runtime
        finally:
            # Guarantee the singleton is cleared even if the client close raises.
            try:
                await runtime.client.aclose()
            finally:
                reset_runtime()

    return lifespan
