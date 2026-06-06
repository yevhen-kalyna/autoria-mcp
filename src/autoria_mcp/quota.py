"""Local request-quota accounting for the AUTO.RIA API.

RIA exposes no ``X-RateLimit-*`` / ``Retry-After`` headers, yet the free package
caps usage at roughly 30 requests/hour and 1000/month, and *breaching* the limit
temporarily blocks the key. The client therefore tracks usage locally so it can
warn before that happens.

This tracker is **warn-only**: :meth:`record` logs a warning once a window
crosses ``limit * warn_ratio`` but never refuses a request. Counts persist to
``cache_dir/quota.json`` (atomic write) so they survive process restarts.
Accounting is best-effort and accurate for a single long-lived process; it does
not coordinate (file-lock) across concurrent processes sharing one key.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import TypedDict

logger = logging.getLogger("autoria_mcp.quota")

_HOUR = 3600.0
# Calendar month is approximated by a fixed 30-day window. The exact reset
# boundary is unknown (RIA does not document it); a rolling window is the safe,
# conservative choice for a warn-only signal.
_MONTH = 30 * 24 * _HOUR


class QuotaUsage(TypedDict):
    """Current usage snapshot for both rolling windows."""

    hour_count: int
    hour_limit: int
    month_count: int
    month_limit: int


class _QuotaState(TypedDict):
    hour_start: float
    hour_count: int
    month_start: float
    month_count: int


class QuotaTracker:
    """Persisted, warn-only request counter with rolling hour/month windows."""

    def __init__(
        self,
        path: Path,
        *,
        hourly_limit: int,
        monthly_limit: int,
        warn_ratio: float,
        time_fn: Callable[[], float] | None = None,
    ) -> None:
        self._path = Path(path)
        self._hourly_limit = hourly_limit
        self._monthly_limit = monthly_limit
        self._warn_ratio = warn_ratio
        self._now: Callable[[], float] = time_fn or time.time
        self._lock = asyncio.Lock()
        self._state: _QuotaState | None = None

    async def record(self) -> None:
        """Count one successful request, rolling windows and warning as needed."""
        async with self._lock:
            now = float(self._now())
            state = self._roll(self._load_locked(), now)
            state["hour_count"] += 1
            state["month_count"] += 1
            self._state = state
            await asyncio.to_thread(self._write, state)
            self._maybe_warn(state)

    async def usage(self) -> QuotaUsage:
        """Return the current usage for both windows (rolls expired windows)."""
        async with self._lock:
            now = float(self._now())
            state = self._roll(self._load_locked(), now)
            self._state = state
            return QuotaUsage(
                hour_count=state["hour_count"],
                hour_limit=self._hourly_limit,
                month_count=state["month_count"],
                month_limit=self._monthly_limit,
            )

    # -- internals -----------------------------------------------------------

    def _load_locked(self) -> _QuotaState:
        """Return cached state, or read it from disk, or start a fresh window."""
        if self._state is not None:
            return _QuotaState(
                hour_start=self._state["hour_start"],
                hour_count=self._state["hour_count"],
                month_start=self._state["month_start"],
                month_count=self._state["month_count"],
            )
        now = float(self._now())
        try:
            raw = self._path.read_text(encoding="utf-8")
            payload = json.loads(raw)
            return _QuotaState(
                hour_start=float(payload["hour_start"]),
                hour_count=int(payload["hour_count"]),
                month_start=float(payload["month_start"]),
                month_count=int(payload["month_count"]),
            )
        except (FileNotFoundError, OSError, ValueError, KeyError, TypeError):
            return _QuotaState(
                hour_start=now,
                hour_count=0,
                month_start=now,
                month_count=0,
            )

    @staticmethod
    def _roll(state: _QuotaState, now: float) -> _QuotaState:
        if now - state["hour_start"] >= _HOUR:
            state["hour_start"] = now
            state["hour_count"] = 0
        if now - state["month_start"] >= _MONTH:
            state["month_start"] = now
            state["month_count"] = 0
        return state

    def _write(self, state: _QuotaState) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(f".{os.getpid()}.tmp")
            tmp.write_text(json.dumps(state), encoding="utf-8")
            os.replace(tmp, self._path)
        except OSError:
            # Accounting is best-effort; never let persistence failure break a call.
            logger.debug("failed to persist quota state to %s", self._path)

    @staticmethod
    def _crossed(count: int, limit: int, ratio: float) -> bool:
        """True only on the request that first pushes the window over the line."""
        if limit <= 0:
            return False
        threshold = limit * ratio
        return count - 1 < threshold <= count

    def _maybe_warn(self, state: _QuotaState) -> None:
        # Warn only on the crossing request, not on every call past the line.
        if self._crossed(state["hour_count"], self._hourly_limit, self._warn_ratio):
            logger.warning(
                "AUTO.RIA hourly quota near limit: %d/%d requests this hour",
                state["hour_count"],
                self._hourly_limit,
            )
        if self._crossed(state["month_count"], self._monthly_limit, self._warn_ratio):
            logger.warning(
                "AUTO.RIA monthly quota near limit: %d/%d requests this month",
                state["month_count"],
                self._monthly_limit,
            )
