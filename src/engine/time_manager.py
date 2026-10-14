"""
Per-move time allocation, so the engine finishes a whole game within its
10-minute budget (own time, per the assignment rules).
"""

import time
from typing import Optional


class Clock:
    """Tracks one player's remaining think time across a whole game."""

    def __init__(self, total_seconds: float) -> None:
        self.remaining_seconds = total_seconds
        self._move_started_at: Optional[float] = None

    def start_move(self) -> None:
        self._move_started_at = time.monotonic()

    def stop_move(self) -> None:
        if self._move_started_at is None:
            return
        elapsed = time.monotonic() - self._move_started_at
        self.remaining_seconds -= elapsed
        self._move_started_at = None

    def time_left(self) -> float:
        return self.remaining_seconds


def allocate_time(remaining_seconds: float, estimated_moves_left: int) -> float:
    """
    PLACEHOLDER budget: split remaining time evenly across an estimate of
    remaining moves, with a safety margin. Tune this (e.g. spend more early,
    less in a near-forced endgame) as you like.
    """
    estimated_moves_left = max(1, estimated_moves_left)
    safety_margin = 0.9
    return safety_margin * remaining_seconds / estimated_moves_left
