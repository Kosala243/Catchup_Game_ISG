"""Informational human-side turn clock for Pygame.

AI clocks remain authoritative and are maintained by engine.time_manager.Clock.
This display clock runs only while the human is to move, never while an AI is
thinking; its time is not used by the tournament engine.
"""
from __future__ import annotations

import math
import time
from typing import Callable, Optional


class TurnClock:
    def __init__(self, seconds: float = 600.0, now: Optional[Callable[[], float]] = None):
        self._now = now if now is not None else time.monotonic
        self.reset(seconds)

    def reset(self, seconds: float = 600.0) -> None:
        if (isinstance(seconds, bool) or not isinstance(seconds, (float, int))
                or not math.isfinite(seconds) or seconds <= 0):
            raise ValueError("seconds must be finite and positive")
        self.remaining = float(seconds)
        self._since: float | None = None

    @property
    def is_running(self) -> bool:
        return self._since is not None

    def time_left(self) -> float:
        if self._since is None:
            return max(0.0, self.remaining)
        return max(0.0, self.remaining - max(0.0, self._now() - self._since))

    def sync(self, should_run: bool) -> None:
        """Start or stop at a change in whose turn it is; never refund time."""
        if should_run == self.is_running:
            return
        if self._since is not None:
            self.remaining = self.time_left()
            self._since = None
        if should_run and self.remaining > 0:
            self._since = self._now()
