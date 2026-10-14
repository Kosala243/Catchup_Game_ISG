"""
Search entry point.

SCAFFOLDING NOTE: `choose_move` currently just plays a random legal turn so the
rest of the program (GUI, tournament mode, self-play) runs end-to-end. The
assignment requires an alpha-beta based engine - that is the core piece you
need to design and implement yourself (GenAI is explicitly not allowed to
write this). `alpha_beta` and `iterative_deepening` below are left as stubs;
once implemented, swap the body of `choose_move` to call them instead.
"""

import random

from ..game.state import GameState, Turn


def choose_move(state: GameState, time_budget_seconds: float) -> Turn:
    """PLACEHOLDER: pick a uniformly random legal turn. Replace with iterative-deepening alpha-beta."""
    max_allowed = state.stones_allowed_this_turn()
    empties = state.legal_cell_choices()
    count = random.randint(1, min(max_allowed, len(empties)))
    return random.sample(empties, count)


def alpha_beta(state: GameState, depth: int, alpha: float, beta: float, colour: str):
    """
    TODO (required by the assignment): implement minimax with alpha-beta pruning.
    Should return (value, best_turn). Use `evaluate()` from .evaluation at your
    depth cutoff. Consider: how you enumerate the 1-3 stone turns efficiently,
    move ordering (see .move_ordering), and transposition table lookups
    (see .transposition_table).
    """
    raise NotImplementedError("Implement your alpha-beta search here")


def iterative_deepening(state: GameState, time_budget_seconds: float, colour: str) -> Turn:
    """
    TODO: repeatedly call alpha_beta with increasing depth until
    time_budget_seconds runs out, returning the best move found at the
    deepest completed depth.
    """
    raise NotImplementedError("Implement iterative deepening here")
