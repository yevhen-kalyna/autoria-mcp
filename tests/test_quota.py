"""QuotaTracker: warn-only accounting with persisted rolling windows."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from autoria_mcp.quota import QuotaTracker


class FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _tracker(path: Path, clock: FakeClock, **over: object) -> QuotaTracker:
    kwargs: dict[str, object] = {
        "hourly_limit": 30,
        "monthly_limit": 1000,
        "warn_ratio": 0.9,
        "time_fn": clock,
    }
    kwargs.update(over)
    return QuotaTracker(path, **kwargs)  # type: ignore[arg-type]


async def test_record_increments_and_persists(cache_dir: Path) -> None:
    clock = FakeClock()
    path = cache_dir / "quota.json"
    tracker = _tracker(path, clock)

    await tracker.record()
    await tracker.record()

    usage = await tracker.usage()
    assert usage["hour_count"] == 2
    assert usage["month_count"] == 2

    # A fresh tracker reads the persisted counts back from disk.
    reread = _tracker(path, clock)
    again = await reread.usage()
    assert again["hour_count"] == 2
    assert again["month_count"] == 2


async def test_hour_window_rolls(cache_dir: Path) -> None:
    clock = FakeClock()
    tracker = _tracker(cache_dir / "quota.json", clock)

    await tracker.record()
    clock.advance(3601)  # just past one hour
    await tracker.record()

    usage = await tracker.usage()
    assert usage["hour_count"] == 1  # hour reset
    assert usage["month_count"] == 2  # month still accumulating


async def test_warns_near_hourly_limit(cache_dir: Path, caplog: pytest.LogCaptureFixture) -> None:
    clock = FakeClock()
    tracker = _tracker(cache_dir / "quota.json", clock, hourly_limit=10, warn_ratio=0.9)

    with caplog.at_level(logging.WARNING, logger="autoria_mcp.quota"):
        for _ in range(10):  # crosses 0.9*10 == 9 at the 9th, then keeps going
            await tracker.record()

    hourly_warnings = [r for r in caplog.records if "hourly quota near limit" in r.message]
    # Warns once, on the crossing request — not on every call past the line.
    assert len(hourly_warnings) == 1


async def test_record_never_raises_on_unwritable_path(tmp_path: Path) -> None:
    # Point at a path whose parent is a file, so writes fail; record must not raise.
    blocker = tmp_path / "afile"
    blocker.write_text("x", encoding="utf-8")
    clock = FakeClock()
    tracker = _tracker(blocker / "quota.json", clock)

    await tracker.record()  # should swallow the OSError
    usage = await tracker.usage()
    assert usage["hour_count"] == 1
