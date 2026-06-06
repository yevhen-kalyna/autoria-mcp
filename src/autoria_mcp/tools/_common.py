"""Shared helpers for the thin endpoint mirrors and dictionary resources.

These endpoints are slow-changing reference data, so they go through the durable
7-day dictionary cache (the same contract :class:`DictionaryResolver` uses): a
cache hit costs no quota, and a cache-write failure never discards an
already-fetched (already quota-spent) response.
"""

from __future__ import annotations

import logging
from typing import Any

from autoria_mcp.cache import make_cache_key
from autoria_mcp.runtime import RuntimeContext

logger = logging.getLogger("autoria_mcp.tools")


async def cached_get(
    rt: RuntimeContext,
    path: str,
    params: dict[str, Any] | None = None,
) -> Any:
    """GET ``path`` through the 7-day dictionary cache and return decoded JSON."""
    key = make_cache_key(path, params)
    cached = await rt.dict_cache.get(key)
    if cached is not None:
        return cached

    raw = await rt.client.get_json(path, params)
    try:
        await rt.dict_cache.set(key, raw, rt.settings.cache_ttl)
    except Exception:  # persistence is best-effort, never fatal
        logger.debug("failed to cache %s", path)
    return raw
