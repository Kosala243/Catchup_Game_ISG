"""Whole-game monotonic clock and conservative move budgeting.

The clock measures only AI thinking time. Opponent input and GUI display time
are not charged. A game starts with 600 seconds by default.
"""
import math
import time
from typing import Callable, Optional


def _finite_nonnegative(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be finite and nonnegative")
    return value


class Clock:
    """Track cumulative AI thinking time across turns and saved sessions."""

    def __init__(
        self, total_seconds: float = 600.0,
        remaining_seconds: Optional[float] = None,
        time_source: Optional[Callable[[], float]] = None,
    ) -> None:
        self.total_seconds = _finite_nonnegative(total_seconds, "total_seconds")
        if self.total_seconds <= 0:
            raise ValueError("total_seconds must be positive")
        remaining = self.total_seconds if remaining_seconds is None else _finite_nonnegative(
            remaining_seconds, "remaining_seconds"
        )
        if remaining > self.total_seconds:
            raise ValueError("remaining_seconds cannot exceed total_seconds")
        self.remaining_seconds = remaining
        self._now = time_source if time_source is not None else time.monotonic
        self._move_started_at: Optional[float] = None

    @property
    def is_running(self) -> bool:
        return self._move_started_at is not None

    def time_left(self) -> float:
        """Include time consumed by the move currently being searched."""
        if self._move_started_at is None:
            return self.remaining_seconds
        elapsed = max(0.0, self._now() - self._move_started_at)
        return max(0.0, self.remaining_seconds - elapsed)

    def start_move(self) -> None:
        if self.is_running:
            raise RuntimeError("clock already running")
        if self.time_left() <= 0:
            raise TimeoutError("the AI's whole-game thinking time has run out")
        self._move_started_at = self._now()

    def stop_move(self) -> float:
        """Charge elapsed wall time once; return the elapsed duration."""
        if self._move_started_at is None:
            return 0.0
        elapsed = max(0.0, self._now() - self._move_started_at)
        self.remaining_seconds = max(0.0, self.remaining_seconds - elapsed)
        self._move_started_at = None
        return elapsed


def allocate_time(remaining_seconds: float, estimated_moves_left: int) -> float:
    """Move budget, conservatively sharing remaining game time.

    The 0.92 fraction leaves time for future moves, Python overhead, and a
    safety margin. The absolute reserve also prevents spending the last
    few milliseconds of the whole-game clock in one search.
    """
    remaining = _finite_nonnegative(remaining_seconds, "remaining_seconds")
    moves = max(1, int(estimated_moves_left))
    if remaining == 0:
        return 0.0
    reserve = min(remaining, max(0.01, remaining * 0.005))
    usable = max(0.0, remaining - reserve)
    return min(usable, 0.92 * remaining / moves)
