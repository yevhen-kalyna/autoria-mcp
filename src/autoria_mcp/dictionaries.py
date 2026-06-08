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

# RIA labels mix Latin and Cyrillic homoglyphs (e.g. body id 2 ships as
# "Унiверсал" with a *Latin* i). Folding the common confusables to Cyrillic lets
# a user's correctly-typed Cyrillic name — and our English aliases below — match
# the stored label. Applied identically to both sides, so it never merges two
# genuinely distinct labels unless they were already visually identical.
_LATIN_TO_CYRILLIC = str.maketrans(
    {
        "a": "а",
        "b": "в",
        "c": "с",
        "e": "е",
        "h": "н",
        "i": "і",
        "k": "к",
        "m": "м",
        "o": "о",
        "p": "р",
        "t": "т",
        "x": "х",
        "y": "у",
    }
)

# English (and a few transliterated) aliases for the localized filter
# vocabularies, normalized lhs -> normalized target label. Consulted only after
# an exact match misses, so they never override a real localized name. An alias
# that resolves to several entries (e.g. "hybrid") surfaces the normal ambiguity
# error rather than guessing.
_FUEL_ALIASES: dict[str, str] = {
    "diesel": "дизель",
    "petrol": "бензин",
    "gasoline": "бензин",
    "gas": "бензин",
    "electric": "електро",
    "ev": "електро",
    "hybrid": "гібрид (hev)",
    "hev": "гібрид (hev)",
    "mhev": "гібрид (mhev)",
    "phev": "гібрид (phev)",
    "reev": "гібрид (reev)",
    "lpg": "газ пропан-бутан / бензин",
    "cng": "газ метан / бензин",
}
_GEARBOX_ALIASES: dict[str, str] = {
    "manual": "ручна / механіка",
    "mt": "ручна / механіка",
    "automatic": "автомат",
    "auto": "автомат",
    "at": "автомат",
    "tiptronic": "типтронік",
    "robot": "робот",
    "amt": "робот",
    "dct": "робот",
    "dsg": "робот",
    "cvt": "варіатор",
    "variator": "варіатор",
}
_BODY_ALIASES: dict[str, str] = {
    "sedan": "седан",
    "saloon": "седан",
    "wagon": "унiверсал",
    "estate": "унiверсал",
    "touring": "унiверсал",
    "avant": "унiверсал",
    "universal": "унiверсал",
    "hatchback": "хетчбек",
    "hatch": "хетчбек",
    "liftback": "ліфтбек",
    "sportback": "ліфтбек",
    "fastback": "ліфтбек",
    "suv": "позашляховик / кросовер",
    "crossover": "позашляховик / кросовер",
    "coupe": "купе",
    "convertible": "кабріолет",
    "cabriolet": "кабріолет",
    "pickup": "пікап",
    "minivan": "мінівен",
    "mpv": "мінівен",
    "limousine": "лімузин",
    "roadster": "родстер",
}


def _normalize(name: str) -> str:
    return name.strip().casefold()


def _fold(name: str) -> str:
    """Normalized form with Latin/Cyrillic homoglyphs folded to Cyrillic."""
    return _normalize(name).translate(_LATIN_TO_CYRILLIC)


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
        return self._match(items, name, what="gearbox", aliases=_GEARBOX_ALIASES)

    async def fuel_id(self, name: str) -> int:
        items = await self._fetch("/auto/type")
        return self._match(items, name, what="fuel type", aliases=_FUEL_ALIASES)

    async def body_id(self, name: str, *, category_id: int = _DEFAULT_CATEGORY) -> int:
        items = await self._fetch(f"/auto/categories/{category_id}/bodystyles")
        return self._match(items, name, what="body style", aliases=_BODY_ALIASES)

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

    def _match(
        self,
        items: list[DictionaryItem],
        name: str,
        *,
        what: str,
        aliases: dict[str, str] | None = None,
    ) -> int:
        """Return the id whose label matches ``name`` (case-insensitive).

        Three tiers, each only tried if the previous misses: (1) exact normalized
        match; (2) English/transliterated alias → exact match; (3) homoglyph-folded
        match (catches RIA's mixed Latin/Cyrillic labels). Raises
        :class:`AutoRiaLookupError` (with candidates) on miss or ambiguity.
        """
        target = _normalize(name)
        exact = [item for item in items if _normalize(item.name) == target]
        if len(exact) == 1:
            return exact[0].id
        if len(exact) > 1:
            raise AutoRiaLookupError(
                f"{what} '{name}' is ambiguous; matches: {self._format(exact)}"
            )

        # Tiers 2+3: translate an English alias, then compare with homoglyphs
        # folded so a Cyrillic/Latin mismatch (or an alias target) still lands.
        wanted = {_fold(target)}
        if aliases and target in aliases:
            wanted.add(_fold(aliases[target]))
        folded = [item for item in items if _fold(item.name) in wanted]
        by_id = {item.id: item for item in folded}
        if len(by_id) == 1:
            return next(iter(by_id.values())).id
        if len(by_id) > 1:
            raise AutoRiaLookupError(
                f"{what} '{name}' is ambiguous; matches: {self._format(list(by_id.values()))}"
            )
        raise AutoRiaLookupError(
            f"unknown {what} '{name}'. Closest matches: {self._candidates(items, name, aliases)}"
        )

    def _candidates(
        self,
        items: list[DictionaryItem],
        name: str,
        aliases: dict[str, str] | None = None,
    ) -> str:
        """Rank near-matches against the folded label set.

        Seeds suggestions from the aliases — both an exact hit and a *fuzzy* match
        against the alias keys — so a misspelt English transliteration (``"Dizel"``)
        still surfaces the intended localized option (``Дизель``) first, instead of
        difflib ranking the Cyrillic label poorly against a Latin-script typo.
        """
        target = _normalize(name)
        folded_to_item: dict[str, DictionaryItem] = {}
        for item in items:  # first label wins for a given folded form
            folded_to_item.setdefault(_fold(item.name), item)

        ordered: list[DictionaryItem] = []
        seen: set[int] = set()

        def _add(item: DictionaryItem) -> None:
            if item.id not in seen:
                seen.add(item.id)
                ordered.append(item)

        # Alias-driven seeds: an exact alias plus alias KEYS close to the input
        # ("dizel" ~ "diesel"). The targets are real labels, so map them directly.
        if aliases:
            keys = [target] if target in aliases else []
            keys += difflib.get_close_matches(target, list(aliases), n=_MAX_CANDIDATES, cutoff=0.6)
            for key in keys:
                seed = folded_to_item.get(_fold(aliases[key]))
                if seed is not None:
                    _add(seed)

        # Then fuzzy-match the input itself against the (homoglyph-folded) labels.
        for hit in difflib.get_close_matches(
            _fold(target), list(folded_to_item), n=_MAX_CANDIDATES, cutoff=0.4
        ):
            _add(folded_to_item[hit])

        if not ordered:
            # Nothing similar — show the first few options so the agent sees the shape.
            return self._format(items[:_MAX_CANDIDATES]) or "(none)"
        return self._format(ordered[:_MAX_CANDIDATES])

    @staticmethod
    def _format(items: list[DictionaryItem]) -> str:
        return ", ".join(f"{item.name} (id={item.id})" for item in items)
