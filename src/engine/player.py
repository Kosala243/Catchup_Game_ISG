"""
AIPlayer: glues the clock, time manager and search together.
"""

from ..game.state import GameState, Turn
from . import search
from .time_manager import Clock, allocate_time


class AIPlayer:
    def __init__(self, colour: str, total_seconds: float = 600.0) -> None:
        self.colour = colour
        self.clock = Clock(total_seconds)

    def choose_move(self, state: GameState, estimated_moves_left: int = 20) -> Turn:
        budget = allocate_time(self.clock.time_left(), estimated_moves_left)
        self.clock.start_move()
        try:
            move = search.choose_move(state, budget)
        finally:
            self.clock.stop_move()
        return move
