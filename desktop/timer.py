"""
timer.py — Dual chess clock.

Time is measured with a monotonic clock that can be injected, which makes the
class deterministic under test.
"""

from __future__ import annotations

import math
import time
from typing import Callable, Dict, Optional

from constants import BLACK, INCREMENT_SECONDS, LOW_TIME_THRESHOLD, RAPID_SECONDS, WHITE


class ChessClock:
    def __init__(self, initial_seconds: float = RAPID_SECONDS,
                 increment: float = INCREMENT_SECONDS,
                 time_source: Callable[[], float] = time.monotonic) -> None:
        self.initial_seconds = float(initial_seconds)
        self.increment = float(increment)
        self._now = time_source
        self._remaining: Dict[str, float] = {WHITE: self.initial_seconds,
                                             BLACK: self.initial_seconds}
        self.active: Optional[str] = None
        self._running = False
        self._last_tick: Optional[float] = None

    # ------------------------------------------------------------------
    @property
    def running(self) -> bool:
        return self._running

    def _sync(self) -> None:
        if self._running and self.active is not None and self._last_tick is not None:
            now = self._now()
            elapsed = now - self._last_tick
            self._remaining[self.active] = max(0.0, self._remaining[self.active] - elapsed)
            self._last_tick = now

    def time_left(self, color: str) -> float:
        self._sync()
        return self._remaining[color]

    # ------------------------------------------------------------------
    def start(self, color: str = WHITE) -> None:
        self.active = color
        self._running = True
        self._last_tick = self._now()

    def switch(self) -> None:
        """Press the clock after a completed move."""
        if self.active is None:
            return
        self._sync()
        self._remaining[self.active] += self.increment
        self.active = BLACK if self.active == WHITE else WHITE
        self._last_tick = self._now()

    def pause(self) -> None:
        self._sync()
        self._running = False

    def resume(self) -> None:
        if self.active is not None and not self._running:
            self._running = True
            self._last_tick = self._now()

    def stop(self) -> None:
        self._sync()
        self._running = False
        self.active = None

    def flagged(self) -> Optional[str]:
        """Return the colour whose time has expired, if any."""
        self._sync()
        if self.active is not None and self._remaining[self.active] <= 0.0:
            return self.active
        return None

    def is_low(self, color: str) -> bool:
        return self.time_left(color) < LOW_TIME_THRESHOLD

    # ------------------------------------------------------------------
    @staticmethod
    def format_time(seconds: float) -> str:
        """'10:00' normally; '0:19.8' (tenths) below the low-time threshold."""
        seconds = max(0.0, seconds)
        if seconds < LOW_TIME_THRESHOLD:
            tenths = int(math.floor(seconds * 10 + 1e-9))
            return f"{tenths // 600}:{(tenths // 10) % 60:02d}.{tenths % 10}"
        whole = int(math.floor(seconds + 1e-9))
        hours, rem = divmod(whole, 3600)
        minutes, secs = divmod(rem, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        return f"{minutes}:{secs:02d}"
