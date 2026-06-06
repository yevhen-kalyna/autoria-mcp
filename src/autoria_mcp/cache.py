"""TTL cache abstraction for AUTO.RIA responses.

Two cache implementations share the :class:`Cache` Protocol:

  * :class:`TwoTierCache` — an in-memory layer (now a bounded LRU) in front of a
    JSON-on-disk store under ``Settings.cache_dir``. Used for the large,
    slow-changing *dictionaries* (marks, models, states, ...), which are cached
    aggressively with a long per-entry TTL and persisted across restarts.
  * :class:`MemoryCache` — a bounded, memory-only LRU with per-entry TTL. Used
    for *volatile* responses (search, statistics) that change quickly and must
    not be written to disk or kept around long.

Design notes:
  * Each entry stores an *absolute* expiry epoch, so disk TTL survives restarts.
  * Disk writes are atomic (temp file in the same dir + ``os.replace``); a
    missing or corrupt file is treated as a cache miss, never an error.
  * Blocking file I/O runs in a worker thread so the async call path never
    blocks the event loop.
  * Cache keys exclude the ``api_key``/``user_id`` query params, so secrets are
    never written to disk and key order never changes the key.
  * The in-memory tier of both caches is a bounded LRU: the least-recently-used
    entry is evicted once ``max_entries`` is exceeded, so a long-running process
    cannot grow memory without limit.

The cache directory must stay out of git (see ``.gitignore``).
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import os
import time
from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path
from typing import Protocol, runtime_checkable
from urllib.parse import urlencode

logger = logging.getLogger("autoria_mcp.cache")

# Query params that must never appear in a cache key (they are secrets and would
# also fragment the key across users).
_SECRET_PARAMS = frozenset({"api_key", "user_id"})


@runtime_checkable
class Cache(Protocol):
    """Minimal async cache contract used by the client and dictionary resolver."""

    async def get(self, key: str) -> object | None:
        """Return the cached value for ``key`` or ``None`` if absent/expired."""
        ...

    async def set(self, key: str, value: object, ttl: int) -> None:
        """Store ``value`` under ``key`` for ``ttl`` seconds."""
        ...

    async def clear(self) -> None:
        """Drop every entry (both tiers)."""
        ...


def make_cache_key(path: str, params: dict[str, object] | None = None) -> str:
    """Build a stable cache key from an endpoint path and its query params.

    The key is ``path`` plus the URL-encoded params sorted by name, with the
    secret params (:data:`_SECRET_PARAMS`) removed. Sorting makes the key
    order-invariant; dropping secrets keeps them off disk and out of logs.
    """
    safe = {
        str(k): "" if v is None else str(v)
        for k, v in (params or {}).items()
        if k not in _SECRET_PARAMS
    }
    if not safe:
        return path
    query = urlencode(sorted(safe.items()))
    return f"{path}?{query}"


class _LruExpiryStore:
    """A bounded, LRU-ordered map of ``key -> (absolute_expiry, value)``.

    Not thread/async-safe on its own — callers hold their cache's lock around
    every method. Eviction is least-recently-used: a ``get`` hit or a ``put``
    moves the key to the most-recently-used end, and ``put`` evicts from the
    least-recently-used end once ``max_entries`` is exceeded.
    """

    def __init__(self, max_entries: int | None) -> None:
        self._max = max_entries
        self._data: OrderedDict[str, tuple[float, object]] = OrderedDict()

    def get(self, key: str, now: float) -> object | None:
        """Return the live value for ``key``, dropping it if expired/absent."""
        entry = self._data.get(key)
        if entry is None:
            return None
        expiry, value = entry
        if expiry <= now:
            del self._data[key]
            return None
        self._data.move_to_end(key)
        return value

    def put(self, key: str, expiry: float, value: object) -> None:
        self._data[key] = (expiry, value)
        self._data.move_to_end(key)
        if self._max is not None:
            while len(self._data) > self._max:
                self._data.popitem(last=False)  # evict least-recently-used

    def delete(self, key: str) -> None:
        self._data.pop(key, None)

    def clear(self) -> None:
        self._data.clear()

    def __len__(self) -> int:
        return len(self._data)


class TwoTierCache:
    """In-memory LRU cache backed by an on-disk JSON store, with per-entry TTL.

    Implements the :class:`Cache` protocol. Construct one per process and share
    it across the client and resolver. The memory tier is a bounded LRU
    (``max_memory_entries``); the disk tier is unbounded but TTL-expiring, so a
    cold process still rehydrates from disk after a restart.
    """

    def __init__(
        self,
        cache_dir: Path,
        *,
        max_memory_entries: int | None = None,
        time_fn: Callable[[], float] | None = None,
    ) -> None:
        self._dir = Path(cache_dir)
        # ``time_fn`` is injectable so tests can control expiry deterministically.
        self._now: Callable[[], float] = time_fn or time.time
        # ``None`` keeps the historical unbounded behavior for callers that omit a cap.
        self._memory = _LruExpiryStore(max_memory_entries)
        self._lock = asyncio.Lock()

    def _path_for(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self._dir / f"{digest}.json"

    async def get(self, key: str) -> object | None:
        # The lock guards the in-memory tier across the disk-read await so a
        # concurrent set()/clear() cannot be lost or resurrected (tier divergence).
        async with self._lock:
            now = float(self._now())

            value = self._memory.get(key, now)
            if value is not None:
                return value

            # Memory miss/expiry: fall through to the (possibly also-expired) disk tier.
            record = await asyncio.to_thread(self._read_disk, self._path_for(key))
            if record is None:
                return None
            expiry, value = record
            if expiry <= now:
                return None
            # Populate the fast tier for subsequent hits this process.
            self._memory.put(key, expiry, value)
            return value

    async def set(self, key: str, value: object, ttl: int) -> None:
        expiry = float(self._now()) + ttl
        async with self._lock:
            self._memory.put(key, expiry, value)
            await asyncio.to_thread(self._write_disk, self._path_for(key), expiry, value)

    async def clear(self) -> None:
        async with self._lock:
            self._memory.clear()
            await asyncio.to_thread(self._clear_disk)

    # -- blocking helpers (run via asyncio.to_thread) ------------------------

    @staticmethod
    def _read_disk(path: Path) -> tuple[float, object] | None:
        """Return ``(expiry, value)`` from ``path`` or ``None`` on any problem."""
        try:
            raw = path.read_text(encoding="utf-8")
        except (FileNotFoundError, OSError):
            return None
        try:
            payload = json.loads(raw)
            expiry = float(payload["expiry"])
            return expiry, payload["value"]
        except (ValueError, KeyError, TypeError):
            # Corrupt/partial file — treat as a miss. Best-effort cleanup.
            logger.debug("discarding corrupt cache file: %s", path.name)
            with contextlib.suppress(OSError):
                path.unlink()
            return None

    def _write_disk(self, path: Path, expiry: float, value: object) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"expiry": expiry, "value": value}, ensure_ascii=False)
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        try:
            tmp.write_text(payload, encoding="utf-8")
            os.replace(tmp, path)  # atomic within the same directory
        except OSError:
            logger.warning("failed to persist cache entry %s", path.name)
            with contextlib.suppress(OSError):
                tmp.unlink()

    def _clear_disk(self) -> None:
        if not self._dir.exists():
            return
        for pattern in ("*.json", "*.tmp"):
            for entry in self._dir.glob(pattern):
                with contextlib.suppress(OSError):
                    entry.unlink()


class MemoryCache:
    """Bounded, memory-only LRU cache with per-entry TTL.

    Implements the :class:`Cache` protocol. Used for volatile responses (search,
    statistics) that change quickly: they live only in process memory for a
    short TTL and are never written to disk. Bounded by ``max_entries`` (LRU
    eviction), so it cannot grow without limit.
    """

    def __init__(
        self,
        max_entries: int,
        *,
        time_fn: Callable[[], float] | None = None,
    ) -> None:
        self._now: Callable[[], float] = time_fn or time.time
        self._store = _LruExpiryStore(max_entries)
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> object | None:
        async with self._lock:
            return self._store.get(key, float(self._now()))

    async def set(self, key: str, value: object, ttl: int) -> None:
        expiry = float(self._now()) + ttl
        async with self._lock:
            self._store.put(key, expiry, value)

    async def clear(self) -> None:
        async with self._lock:
            self._store.clear()
