"""Depth-limited alpha-beta for Catchup complete turns.

By default the midgame tree is deliberately *selective*: it searches only a
ranked subset of all legal turns. `full_width=True` disables the reduction,
which gives exact alpha-beta/minimax over the specified horizon and is intended
for small positions/tests. Deep search uses make/undo, not costly state copies.
"""
from dataclasses import dataclass
import math
import time
from typing import Optional, Tuple

from ..board.board import BLACK, WHITE
from ..game.state import GameState, Turn
from .evaluation import evaluate
from .move_generation import (
    SearchTimeout,
    check_deadline,
    ranked_candidate_turns,
)


@dataclass
class SearchStats:
    nodes: int = 0
    leaves: int = 0
    cutoffs: int = 0
    searched_moves: int = 0
    completed_depth: int = 0
    timed_out: bool = False


def alpha_beta(
    state: GameState,
    depth: int,
    alpha: float,
    beta: float,
    colour: str,
    *,
    max_branch: int = 12,
    max_cells: int = 14,
    full_width: bool = False,
    deadline: Optional[float] = None,
    stats: Optional[SearchStats] = None,
) -> Tuple[float, Optional[Turn]]:
    """Alpha-beta with values always from `colour`'s perspective.

    One ply means one COMPLETE turn of one to three stones. `state` is restored
    before return, including if a deadline interrupts search.
    """
    if depth < 0:
        raise ValueError("search depth cannot be negative")
    if colour not in (WHITE, BLACK):
        raise ValueError(f"invalid search colour: {colour!r}")
    if alpha > beta:
        raise ValueError("alpha must not exceed beta")
    if stats is None:
        stats = SearchStats()

    def visit(remaining: int, a: float, b: float):
        check_deadline(deadline)
        stats.nodes += 1
        if remaining == 0 or state.is_game_over():
            stats.leaves += 1
            return evaluate(state, colour), None

        choices = ranked_candidate_turns(
            state, max_branch=max_branch, max_cells=max_cells,
            full_width=full_width, deadline=deadline,
        )
        if not choices:
            # Should only occur for a full board, handled above.
            stats.leaves += 1
            return evaluate(state, colour), None

        maximizing = state.to_move == colour
        best_value = -math.inf if maximizing else math.inf
        best_turn = None
        for choice in choices:
            check_deadline(deadline)
            state.apply_turn(choice)
            try:
                value, _ = visit(remaining - 1, a, b)
            finally:
                state.undo()
            stats.searched_moves += 1
            if maximizing:
                if value > best_value:
                    best_value = value
                    best_turn = choice
                a = max(a, best_value)
            else:
                if value < best_value:
                    best_value = value
                    best_turn = choice
                b = min(b, best_value)
            if a >= b:
                stats.cutoffs += 1
                break
        return best_value, list(best_turn) if best_turn is not None else None

    return visit(depth, alpha, beta)


def iterative_deepening(
    state: GameState,
    time_budget_seconds: float,
    colour: str,
    *,
    max_depth: int = 3,
    max_branch: int = 12,
    max_cells: int = 14,
    full_width: bool = False,
    stats: Optional[SearchStats] = None,
) -> Turn:
    """Return the move from the deepest fully completed search iteration.

    If the deadline hits, keep the best move from the PREVIOUS iteration.
    An immediately available legal fallback is retained for tiny budgets.
    """
    if state.is_game_over():
        raise ValueError("cannot search for a move after the game has ended")
    if colour != state.to_move:
        raise ValueError("search colour must be the side to move")
    if max_depth < 1:
        raise ValueError("max_depth must be at least one")
    if stats is None:
        stats = SearchStats()

    deadline = time.monotonic() + max(0.0, time_budget_seconds)
    # Get a legal fallback even if time is already exhausted.
    fallback = next(iter(ranked_candidate_turns(
        state, max_branch=max_branch, max_cells=max_cells, full_width=False,
    )))
    best_completed = fallback
    for depth in range(1, max_depth + 1):
        try:
            _, candidate = alpha_beta(
                state, depth, -math.inf, math.inf, colour,
                max_branch=max_branch, max_cells=max_cells,
                full_width=full_width, deadline=deadline, stats=stats,
            )
        except SearchTimeout:
            stats.timed_out = True
            break
        if candidate is not None:
            best_completed = candidate
            stats.completed_depth = depth
    return list(best_completed)


def choose_move(state: GameState, time_budget_seconds: float) -> Turn:
    """Public engine API used by all existing game modes."""
    return iterative_deepening(
        state, time_budget_seconds, state.to_move,
        max_depth=3, max_branch=12, max_cells=14,
    )