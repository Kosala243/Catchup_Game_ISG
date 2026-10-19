"""Player integration: per-game clock and search allocation."""
import math
from typing import Optional

from ..board.board import BLACK, WHITE
from ..game.state import GameState, Turn
from . import search
from .move_ordering import MoveOrdering
from .transposition_table import TranspositionTable
from .time_manager import Clock, allocate_time

class AIPlayer:
    def __init__(
        self, colour: str, total_seconds: float = 600.0,
        remaining_seconds: Optional[float] = None,
    ) -> None:
        if colour not in (WHITE, BLACK):
            raise ValueError("AI colour must be W or B")
        self.colour = colour
        self.clock = Clock(total_seconds, remaining_seconds=remaining_seconds)
        # Separate, bounded search caches per AI/colour and game.
        self._table = TranspositionTable(max_entries=50_000)
        self._ordering = MoveOrdering()

    def move_budget(
        self, state: GameState, estimated_moves_left: Optional[int] = None,
    ) -> float:
        if state.to_move != self.colour or state.is_game_over():
            raise ValueError("AI must be the side to move in a nonterminal state")
        empties = len(state.board.empty_cells())
        estimate = max(1, math.ceil(empties / 3)) if estimated_moves_left is None else estimated_moves_left
        return allocate_time(self.clock.time_left(), estimate)

    def choose_move(
        self, state: GameState, estimated_moves_left: Optional[int] = None,
    ) -> Turn:
        if self.clock.time_left() <= 0:
            raise TimeoutError("AI thinking time exhausted")
        budget = self.move_budget(state, estimated_moves_left)
        self.clock.start_move()
        try:
            with search.shared_search_cache(self._table, self._ordering):
                return search.choose_move(state, budget)
        finally:
            self.clock.stop_move()