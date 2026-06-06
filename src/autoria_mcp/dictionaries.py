"""Name <-> ID resolution for AUTO.RIA dictionaries.

Search parameters are numeric IDs (``marka_id``, ``model_id``, ``state_id``,
gearbox, fuel, body type, ...). Curated tools accept human-friendly names and
resolve them here, against the cached dictionary endpoints. IDs are *never*
hardcoded — they are always resolved through this layer.

Phase 2 defines the resolver shape; the cached lookups and fuzzy matching land
in Phase 3 on top of :class:`autoria_mcp.client.AutoRiaClient` and the cache.
"""

from __future__ import annotations

import logging

from autoria_mcp.cache import Cache
from autoria_mcp.client import AutoRiaClient

logger = logging.getLogger("autoria_mcp.dictionaries")


class DictionaryResolver:
    """Resolve human-friendly names to AUTO.RIA numeric IDs (and back).

    Backed by the client (for fetches) and the cache (dictionaries are large and
    slow-changing, so they are cached with a long TTL).
    """

    def __init__(self, client: AutoRiaClient, cache: Cache) -> None:
        self._client = client
        self._cache = cache

    async def brand_id(self, name: str) -> int:
        """Resolve a brand/marque name (e.g. ``"BMW"``) to its ``marka_id``.

        Raises:
            NotImplementedError: until Phase 3.
        """
        # TODO(phase 3): fetch /auto/categories/.../marks (cached), normalize the
        # query, match case-insensitively across UK/RU/EN labels, raise a clear
        # error listing near-matches when ambiguous/not found.
        raise NotImplementedError("DictionaryResolver.brand_id lands in Phase 3")

    async def model_id(self, brand: str, model: str) -> int:
        """Resolve a (brand, model) pair to its ``model_id``.

        Raises:
            NotImplementedError: until Phase 3.
        """
        raise NotImplementedError("DictionaryResolver.model_id lands in Phase 3")

    async def region_id(self, name: str) -> int:
        """Resolve a region/oblast name to its ``state_id``.

        Raises:
            NotImplementedError: until Phase 3.
        """
        raise NotImplementedError("DictionaryResolver.region_id lands in Phase 3")
