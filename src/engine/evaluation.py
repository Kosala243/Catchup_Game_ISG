"""
Heuristic evaluation function.

SCAFFOLDING NOTE: this is a deliberately trivial placeholder (score
difference only) so search has something to call. The assignment explicitly
says GenAI must not write your evaluation function - design and implement
your own, and disclose in AI_USAGE.md if any part of this stub remains.
"""

from ..board.board import other
from ..board.groups import largest_group_size
from ..game.state import GameState


def evaluate(state: GameState, colour: str) -> float:
    """Positive favours `colour`. Placeholder: current largest-group difference."""
    mine = largest_group_size(state.board, colour)
    theirs = largest_group_size(state.board, other(colour))
    return float(mine - theirs)
