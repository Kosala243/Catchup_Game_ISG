"""Alpha-beta with incremental exact position keys and safe TT cutoffs.

Search remains SELECTIVE by default (top candidate turns, not all legal
turns). `full_width=True` is exact within the chosen depth horizon.
Every complete turn is one ply. All make/undo operations are exception-safe.
"""
from dataclasses import dataclass
import math
import time
from typing import Optional, Tuple

from ..board.board import BLACK, WHITE
from ..game.state import GameState, Turn
from .evaluation import evaluate
from .move_generation import SearchTimeout, check_deadline, ranked_candidate_turns
from .move_ordering import MoveOrdering
from .transposition_table import (
    Bound, TTEntry, TranspositionTable, occupancy_bits, position_key, turn_mask,
)


@dataclass
class SearchStats:
    nodes: int = 0
    leaves: int = 0
    cutoffs: int = 0
    searched_moves: int = 0
    completed_depth: int = 0
    timed_out: bool = False
    tt_hits: int = 0
    tt_cutoffs: int = 0
    tt_stores: int = 0
    generated_moves: int = 0


def alpha_beta(
    state: GameState, depth: int, alpha: float, beta: float, colour: str,
    *, max_branch: int = 12, max_cells: int = 14,
    full_width: bool = False, deadline: Optional[float] = None,
    stats: Optional[SearchStats] = None,
    table: Optional[TranspositionTable] = None,
    ordering: Optional[MoveOrdering] = None,
    use_tt: bool = True, use_ordering: bool = True,
) -> Tuple[float, Optional[Turn]]:
    """Minimax with alpha-beta pruning, scored from `colour`'s perspective.

    Optional `table` can be reused for iterative deepening at a fixed search
    configuration. The key includes the configuration and perspective to avoid
    mixing incompatible results.
    """
    if depth < 0:
        raise ValueError("search depth cannot be negative")
    if colour not in (WHITE, BLACK):
        raise ValueError(f"invalid search colour: {colour!r}")
    if alpha >= beta:
        raise ValueError("alpha must be less than beta")
    if max_branch < 1 or max_cells < 1:
        raise ValueError("max_branch and max_cells must be positive")
    if stats is None:
        stats = SearchStats()
    if table is None and use_tt:
        table = TranspositionTable()
    if ordering is None and use_ordering:
        ordering = MoveOrdering()

    root_white, root_black = occupancy_bits(state)

    def visit(remaining: int, a: float, b: float, white_bits: int, black_bits: int):
        check_deadline(deadline)
        stats.nodes += 1
        if remaining == 0 or state.is_game_over():
            stats.leaves += 1
            return evaluate(state, colour), None

        original_alpha, original_beta = a, b
        key = position_key(state, colour, max_branch, max_cells, full_width,
                           masks=(white_bits, black_bits))
        entry = table.get(key) if use_tt and table is not None else None
        if entry is not None:
            stats.tt_hits += 1
            if entry.depth >= remaining:
                if entry.bound == Bound.EXACT:
                    stats.tt_cutoffs += 1
                    return entry.value, list(entry.best_move) if entry.best_move else None
                if entry.bound == Bound.LOWER:
                    a = max(a, entry.value)
                elif entry.bound == Bound.UPPER:
                    b = min(b, entry.value)
                if a >= b:
                    stats.tt_cutoffs += 1
                    return entry.value, list(entry.best_move) if entry.best_move else None

        choices = ranked_candidate_turns(
            state, max_branch=max_branch, max_cells=max_cells,
            full_width=full_width, deadline=deadline,
        )
        stats.generated_moves += len(choices)
        if not choices:
            stats.leaves += 1
            return evaluate(state, colour), None

        mover = state.to_move
        maximizing = mover == colour
        if use_ordering and ordering is not None:
            choices = ordering.order_moves(
                choices, mover, remaining,
                pv_move=entry.best_move if entry else None,
            )

        best_value = -math.inf if maximizing else math.inf
        best_turn = None
        for choice in choices:
            check_deadline(deadline)
            bits = turn_mask(choice)
            state.apply_turn(choice)
            try:
                if mover == WHITE:
                    value, _ = visit(remaining - 1, a, b, white_bits | bits, black_bits)
                else:
                    value, _ = visit(remaining - 1, a, b, white_bits, black_bits | bits)
            finally:
                state.undo()
            stats.searched_moves += 1
            if maximizing:
                if value > best_value:
                    best_value, best_turn = value, choice
                a = max(a, best_value)
            else:
                if value < best_value:
                    best_value, best_turn = value, choice
                b = min(b, best_value)
            if a >= b:
                stats.cutoffs += 1
                if use_ordering and ordering is not None:
                    ordering.record_cutoff(mover, remaining, choice)
                break

        if use_tt and table is not None:
            if best_value <= original_alpha:
                bound = Bound.UPPER
            elif best_value >= original_beta:
                bound = Bound.LOWER
            else:
                bound = Bound.EXACT
            stored = table.store(
                key, TTEntry(remaining, best_value, bound,
                             tuple(best_turn) if best_turn is not None else None)
            )
            if stored:
                stats.tt_stores += 1
        return best_value, list(best_turn) if best_turn is not None else None

    return visit(depth, alpha, beta, root_white, root_black)


def iterative_deepening(
    state: GameState, time_budget_seconds: float, colour: str,
    *, max_depth: int = 4, max_branch: int = 12, max_cells: int = 14,
    full_width: bool = False, stats: Optional[SearchStats] = None,
    use_tt: bool = True, use_ordering: bool = True,
) -> Turn:
    """Use the deepest *completed* iteration; never return an interrupted PV."""
    if state.is_game_over():
        raise ValueError("cannot search for a move after the game has ended")
    if colour != state.to_move:
        raise ValueError("search colour must be the side to move")
    if max_depth < 1:
        raise ValueError("max_depth must be at least one")
    if stats is None:
        stats = SearchStats()

    deadline = time.monotonic() + max(0.0, time_budget_seconds)
    # O(1) fallback to respect very small time budgets. It is intentionally
    # unoptimized, but always legal (the player may place one stone).
    fallback = [state.board.empty_cells()[0]]
    best_completed = fallback
    table = TranspositionTable() if use_tt else None
    ordering = MoveOrdering() if use_ordering else None
    for current_depth in range(1, max_depth + 1):
        try:
            _, candidate = alpha_beta(
                state, current_depth, -math.inf, math.inf, colour,
                max_branch=max_branch, max_cells=max_cells,
                full_width=full_width, deadline=deadline, stats=stats,
                table=table, ordering=ordering,
                use_tt=use_tt, use_ordering=use_ordering,
            )
        except SearchTimeout:
            stats.timed_out = True
            break
        if candidate is not None:
            best_completed = candidate
            stats.completed_depth = current_depth
    return list(best_completed)


def choose_move(state: GameState, time_budget_seconds: float) -> Turn:
    """Public API used by GUI, tournament relay, and self-play."""
    return iterative_deepening(state, time_budget_seconds, state.to_move)