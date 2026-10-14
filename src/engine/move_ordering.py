"""
Move ordering for alpha-beta.

SCAFFOLDING NOTE: identity placeholder (no ordering). Move ordering has a big
effect on alpha-beta's effective branching factor - consider killer moves,
history heuristic, or evaluation-guided ordering here.
"""

from typing import List

from ..game.state import GameState, Turn


def order_moves(moves: List[Turn], state: GameState) -> List[Turn]:
    """TODO: reorder `moves` to search the most promising ones first."""
    return moves
