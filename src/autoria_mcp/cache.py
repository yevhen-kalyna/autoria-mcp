"""TTL cache abstraction for slow-changing dictionary data.

Phase 3 implements :class:`TwoTierCache`: an in-memory layer in front of a
JSON-on-disk store under ``Settings.cache_dir``. Dictionary endpoints (marks,
models, states, ...) change slowly and are expensive against the scarce API
quota, so they are cached aggressively with a long per-entry TTL.

Design notes:
  * Each entry stores an *absolute* expiry epoch, so TTL survives restarts.
  * Disk writes are atomic (temp file in the same dir + ``os.replace``); a
    missing or corrupt file is treated as a cache miss, never an error.
  * Blocking file I/O runs in a worker thread so the async call path never
    blocks the event loop.
  * Cache keys exclude the ``api_key``/``user_id`` query params, so secrets are
    never written to disk and key order never changes the key.

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


class TwoTierCache:
    """In-memory cache backed by an on-disk JSON store, with per-entry TTL.

    Implements the :class:`Cache` protocol. Construct one per process and share
    it across the client and resolver.
    """

    def __init__(
        self,
        cache_dir: Path,
        *,
        time_fn: Callable[[], float] | None = None,
    ) -> None:
        self._dir = Path(cache_dir)
        # ``time_fn`` is injectable so tests can control expiry deterministically.
        self._now: Callable[[], float] = time_fn or time.time
        self._memory: dict[str, tuple[float, object]] = {}
        self._lock = asyncio.Lock()

    def _path_for(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self._dir / f"{digest}.json"

    async def get(self, key: str) -> object | None:
        # The lock guards the in-memory tier across the disk-read await so a
        # concurrent set()/clear() cannot be lost or resurrected (tier divergence).
        async with self._lock:
            now = float(self._now())

            cached = self._memory.get(key)
            if cached is not None:
                expiry, value = cached
                if expiry > now:
                    return value
                # Expired: drop from memory and fall through to (also-expired) disk.
                del self._memory[key]

            record = await asyncio.to_thread(self._read_disk, self._path_for(key))
            if record is None:
                return None
            expiry, value = record
            if expiry <= now:
                return None
            # Populate the fast tier for subsequent hits this process.
            self._memory[key] = (expiry, value)
            return value

    async def set(self, key: str, value: object, ttl: int) -> None:
        expiry = float(self._now()) + ttl
        async with self._lock:
            self._memory[key] = (expiry, value)
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
