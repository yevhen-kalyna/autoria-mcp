"""Name <-> ID resolution for AUTO.RIA dictionaries.

Search parameters are numeric IDs (``marka_id``, ``model_id``, ``state_id``,
gearbox, fuel, body type, ...). Curated tools accept human-friendly names and
resolve them here, against the cached dictionary endpoints. IDs are *never*
hardcoded — they are always resolved through this layer.

Matching is case-insensitive across the mixed UK/RU/EN labels RIA returns. On a
miss or an ambiguous match the resolver raises :class:`AutoRiaLookupError` with
the nearest candidates (id + label) so an agent can recover without guessing.
"""

from __future__ import annotations

import asyncio
import difflib
import logging

from autoria_mcp.cache import Cache, make_cache_key
from autoria_mcp.client import AutoRiaClient, AutoRiaLookupError
from autoria_mcp.models import DictionaryItem, parse_dictionary

logger = logging.getLogger("autoria_mcp.dictionaries")

# Default transport category: 1 == passenger cars. Category-scoped dictionary
# endpoints use this unless a caller overrides it.
_DEFAULT_CATEGORY = 1
# How many near-matches to surface when a lookup fails.
_MAX_CANDIDATES = 5


def _normalize(name: str) -> str:
    return name.strip().casefold()


class DictionaryResolver:
    """Resolve human-friendly names to AUTO.RIA numeric IDs.

    Backed by the client (for fetches) and the cache (dictionaries are large and
    slow-changing, so they are cached with the long ``Settings.cache_ttl``).
    """

    def __init__(self, client: AutoRiaClient, cache: Cache) -> None:
        self._client = client
        self._cache = cache
        # Per-path single-flight: concurrent cold misses on the same dictionary
        # must collapse into one upstream fetch, or they double-spend quota.
        self._fetch_locks: dict[str, asyncio.Lock] = {}
        self._locks_guard = asyncio.Lock()

    # -- public resolvers ----------------------------------------------------

    async def category_id(self, name: str) -> int:
        items = await self._fetch("/auto/categories")
        return self._match(items, name, what="category")

    async def brand_id(self, name: str, *, category_id: int = _DEFAULT_CATEGORY) -> int:
        """Resolve a brand/marque name (e.g. ``"BMW"``) to its ``marka_id``."""
        items = await self._fetch(f"/auto/categories/{category_id}/marks")
        return self._match(items, name, what="brand")

    async def model_id(
        self, brand: str, model: str, *, category_id: int = _DEFAULT_CATEGORY
    ) -> int:
        """Resolve a (brand, model) pair to its ``model_id`` within that brand."""
        marka_id = await self.brand_id(brand, category_id=category_id)
        items = await self._fetch(f"/auto/categories/{category_id}/marks/{marka_id}/models")
        return self._match(items, model, what=f"model of {brand}")

    async def region_id(self, name: str) -> int:
        """Resolve a region/oblast name to its ``state_id``."""
        items = await self._fetch("/auto/states")
        return self._match(items, name, what="region")

    async def city_id(self, region: str, city: str) -> int:
        """Resolve a (region, city) pair to its city id within that region."""
        state_id = await self.region_id(region)
        items = await self._fetch(f"/auto/states/{state_id}/cities")
        return self._match(items, city, what=f"city in {region}")

    async def gearbox_id(self, name: str, *, category_id: int = _DEFAULT_CATEGORY) -> int:
        items = await self._fetch(f"/auto/categories/{category_id}/gearboxes")
        return self._match(items, name, what="gearbox")

    async def fuel_id(self, name: str) -> int:
        items = await self._fetch("/auto/type")
        return self._match(items, name, what="fuel type")

    async def body_id(self, name: str, *, category_id: int = _DEFAULT_CATEGORY) -> int:
        items = await self._fetch(f"/auto/categories/{category_id}/bodystyles")
        return self._match(items, name, what="body style")

    async def drive_id(self, name: str, *, category_id: int = _DEFAULT_CATEGORY) -> int:
        items = await self._fetch(f"/auto/categories/{category_id}/driverTypes")
        return self._match(items, name, what="drive type")

    async def color_id(self, name: str) -> int:
        items = await self._fetch("/auto/colors")
        return self._match(items, name, what="color")

    # -- internals -----------------------------------------------------------

    async def _fetch(self, path: str) -> list[DictionaryItem]:
        """Return the (cached) dictionary at ``path`` as parsed items.

        Concurrent cold misses on the same path collapse into a single upstream
        fetch via a per-path lock with a double-checked cache read.
        """
        key = make_cache_key(path)
        cached = await self._cache.get(key)
        if cached is not None:
            return parse_dictionary(cached)

        async with await self._lock_for(path):
            # Another coroutine may have populated the cache while we waited.
            cached = await self._cache.get(key)
            if cached is not None:
                return parse_dictionary(cached)

            raw = await self._client.get_json(path)
            # A cache-write failure must not discard an already-fetched (and
            # already quota-spent) response — persist best-effort, then parse.
            try:
                await self._cache.set(key, raw, self._client.settings.cache_ttl)
            except Exception:  # persistence is best-effort, never fatal
                logger.debug("failed to cache dictionary %s", path)
            return parse_dictionary(raw)

    async def _lock_for(self, path: str) -> asyncio.Lock:
        """Return the (lazily created) single-flight lock for ``path``."""
        async with self._locks_guard:
            lock = self._fetch_locks.get(path)
            if lock is None:
                lock = asyncio.Lock()
                self._fetch_locks[path] = lock
            return lock

    def _match(self, items: list[DictionaryItem], name: str, *, what: str) -> int:
        """Return the id whose label matches ``name`` (case-insensitive).

        Raises :class:`AutoRiaLookupError` (with candidates) on miss or ambiguity.
        """
        target = _normalize(name)
        exact = [item for item in items if _normalize(item.name) == target]
        if len(exact) == 1:
            return exact[0].id
        if len(exact) > 1:
            raise AutoRiaLookupError(
                f"{what} '{name}' is ambiguous; matches: {self._format(exact)}"
            )
        raise AutoRiaLookupError(
            f"unknown {what} '{name}'. Closest matches: {self._candidates(items, name)}"
        )

    def _candidates(self, items: list[DictionaryItem], name: str) -> str:
        names = [item.name for item in items]
        close = difflib.get_close_matches(name, names, n=_MAX_CANDIDATES, cutoff=0.4)
        if not close:
            # Nothing similar — show the first few options so the agent sees the shape.
            return self._format(items[:_MAX_CANDIDATES]) or "(none)"
        by_name = {item.name: item for item in items}
        return self._format([by_name[n] for n in close])

    @staticmethod
    def _format(items: list[DictionaryItem]) -> str:
        return ", ".join(f"{item.name} (id={item.id})" for item in items)
