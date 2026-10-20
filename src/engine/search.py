"""Time-limited selective alpha-beta search with tactical exact endgames.

Every ply is one entire Catchup turn. Per-player caches are optional and
bounded; they are keyed by exact board occupancy, rule state, perspective,
search settings and the endgame full-width threshold. Search never changes
its caller's GameState after returning (including timeout paths).
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import math
import time
from typing import Optional, Tuple

from ..board.board import BLACK, WHITE
from ..game.state import GameState, Turn
from .evaluation import evaluate, active_evaluation_variant
from .move_generation import SearchTimeout, check_deadline, ranked_candidate_turns
from .move_ordering import MoveOrdering
from .transposition_table import (
    Bound, TTEntry, TranspositionTable, occupancy_bits, position_key, turn_mask,
)

# ContextVar is worker/thread safe. The public choose_move(state, budget) API
# stays unchanged; player.py can nevertheless provide its own cache per AI.
_SEARCH_CACHE: ContextVar[tuple | None] = ContextVar('catchup_search_cache', default=None)
_SEARCH_PROGRESS: ContextVar[object | None] = ContextVar('catchup_search_progress', default=None)


@contextmanager
def capture_search_progress(callback):
    """Send immutable completed-depth reports to a worker-safe callback."""
    token = _SEARCH_PROGRESS.set(callback)
    try:
        yield
    finally:
        _SEARCH_PROGRESS.reset(token)



@contextmanager
def shared_search_cache(table: TranspositionTable, ordering: MoveOrdering):
    token = _SEARCH_CACHE.set((table, ordering))
    try:
        yield
    finally:
        _SEARCH_CACHE.reset(token)


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
    endgame_full_width_nodes: int = 0
    tactical_extensions: int = 0


def alpha_beta(
    state: GameState, depth: int, alpha: float, beta: float, colour: str,
    *, max_branch: int = 12, max_cells: int = 14,
    full_width: bool = False, deadline: Optional[float] = None,
    stats: Optional[SearchStats] = None,
    table: Optional[TranspositionTable] = None,
    ordering: Optional[MoveOrdering] = None,
    use_tt: bool = True, use_ordering: bool = True,
    endgame_full_width_cells: int = 7,
    tactical_extensions: int = 0,
    tactical_growth: int = 3,
) -> Tuple[float, Optional[Turn]]:
    """Return (evaluation, best legal complete turn) from colour's viewpoint.

    Selective except for explicitly requested full width or small endgames.
    Endgame full-width does not mean unlimited depth: it is exact only
    within the depth horizon or once the board has become terminal.
    """
    if depth < 0:
        raise ValueError('search depth cannot be negative')
    if colour not in (WHITE, BLACK):
        raise ValueError('invalid search colour')
    if not alpha < beta:
        raise ValueError('alpha must be less than beta')
    if max_branch < 1 or max_cells < 1:
        raise ValueError('max_branch and max_cells must be positive')
    if isinstance(endgame_full_width_cells, bool) or not isinstance(endgame_full_width_cells, int) or not (0 <= endgame_full_width_cells <= 10):
        raise ValueError('endgame_full_width_cells must be an integer in 0..10')
    if isinstance(tactical_extensions, bool) or not isinstance(tactical_extensions, int) or not 0 <= tactical_extensions <= 2:
        raise ValueError('tactical_extensions must be 0, 1, or 2')
    if isinstance(tactical_growth, bool) or not isinstance(tactical_growth, int) or tactical_growth < 1:
        raise ValueError('tactical_growth must be a positive integer')
    if stats is None:
        stats = SearchStats()
    if table is None and use_tt:
        table = TranspositionTable()
    if ordering is None and use_ordering:
        ordering = MoveOrdering()

    root_w, root_b = occupancy_bits(state)

    def visit(remaining: int, a: float, b: float, w: int, k: int, extensions_left: int):
        check_deadline(deadline)
        stats.nodes += 1
        if remaining == 0 or state.is_game_over():
            stats.leaves += 1
            return evaluate(state, colour), None

        vacancy_count = len(state.board.empty_cells())
        locally_exhaustive = full_width or (0 < endgame_full_width_cells and vacancy_count <= endgame_full_width_cells)
        if locally_exhaustive and not full_width:
            stats.endgame_full_width_nodes += 1
        key = position_key(
            state, colour, max_branch, max_cells, locally_exhaustive,
            masks=(w, k), endgame_full_width_cells=endgame_full_width_cells,
            extensions_left=extensions_left, extension_growth=tactical_growth,
            evaluation_id=active_evaluation_variant(),
        )
        original_a, original_b = a, b
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
            full_width=locally_exhaustive, deadline=deadline,
        )
        stats.generated_moves += len(choices)
        if not choices:
            stats.leaves += 1
            return evaluate(state, colour), None
        mover = state.to_move
        maximizing = mover == colour
        if use_ordering and ordering is not None:
            choices = ordering.order_moves(
                choices, mover, remaining, pv_move=entry.best_move if entry else None,
            )

        best_value = -math.inf if maximizing else math.inf
        best_turn = None
        for turn in choices:
            check_deadline(deadline)
            mask = turn_mask(turn)
            score_before = state.scores[mover]
            state.apply_turn(turn)
            try:
                # A bounded selective extension at the nominal search horizon.
                # It is NOT an unlimited extension of every tactical subtree.
                extend = (remaining == 1 and extensions_left > 0
                          and not state.is_game_over()
                          and (state.scores[mover] - score_before >= tactical_growth
                               or state.stones_allowed_this_turn() == 3))
                if extend:
                    stats.tactical_extensions += 1
                child_depth = remaining - 1 + (1 if extend else 0)
                child_extensions = extensions_left - (1 if extend else 0)
                if mover == WHITE:
                    value, _ = visit(child_depth, a, b, w | mask, k, child_extensions)
                else:
                    value, _ = visit(child_depth, a, b, w, k | mask, child_extensions)
            finally:
                state.undo()
            stats.searched_moves += 1
            if maximizing:
                if value > best_value:
                    best_value, best_turn = value, turn
                a = max(a, best_value)
            else:
                if value < best_value:
                    best_value, best_turn = value, turn
                b = min(b, best_value)
            if a >= b:
                stats.cutoffs += 1
                if use_ordering and ordering is not None:
                    ordering.record_cutoff(mover, remaining, turn)
                break

        if use_tt and table is not None:
            bound = (Bound.UPPER if best_value <= original_a else
                     Bound.LOWER if best_value >= original_b else Bound.EXACT)
            stored = table.store(key, TTEntry(
                remaining, best_value, bound,
                tuple(best_turn) if best_turn is not None else None,
            ))
            if stored:
                stats.tt_stores += 1
        return best_value, list(best_turn) if best_turn is not None else None

    return visit(depth, alpha, beta, root_w, root_b, tactical_extensions)


def iterative_deepening(
    state: GameState, time_budget_seconds: float, colour: str,
    *, max_depth: int = 6, max_branch: int = 12, max_cells: int = 14,
    full_width: bool = False, stats: Optional[SearchStats] = None,
    use_tt: bool = True, use_ordering: bool = True,
    table: Optional[TranspositionTable] = None,
    ordering: Optional[MoveOrdering] = None,
    endgame_full_width_cells: int = 7,
    tactical_extensions: int = 1,
    tactical_growth: int = 3,
) -> Turn:
    """Iterate to at most max_depth or until the shared move deadline.

    Retains the deepest FULLY finished iteration, never an interrupted turn.
    Shared caches can persist between AIPlayer calls; default direct callers
    get fresh per-search caches.
    """
    if state.is_game_over():
        raise ValueError('cannot search a completed game')
    if colour != state.to_move:
        raise ValueError('search colour must be side to move')
    if max_depth < 1:
        raise ValueError('max_depth must be positive')
    if isinstance(time_budget_seconds, bool) or not isinstance(time_budget_seconds, (float, int)) or not math.isfinite(time_budget_seconds) or time_budget_seconds < 0:
        raise ValueError('time_budget_seconds must be finite')
    if stats is None:
        stats = SearchStats()
    deadline = time.monotonic() + max(0.0, float(time_budget_seconds))
    best = [state.board.empty_cells()[0]]  # one-stone legal fallback
    if table is None and use_tt:
        table = TranspositionTable()
    if ordering is None and use_ordering:
        ordering = MoveOrdering()
    progress_callback = _SEARCH_PROGRESS.get()
    from ..game.notation import format_turn
    last_counts = {name: 0 for name in (
        'nodes', 'leaves', 'cutoffs', 'tt_hits', 'tt_stores',
        'generated_moves', 'tactical_extensions', 'endgame_full_width_nodes',
    )}
    for depth in range(1, max_depth + 1):
        iteration_started = time.monotonic()
        try:
            value, candidate = alpha_beta(
                state, depth, -math.inf, math.inf, colour,
                max_branch=max_branch, max_cells=max_cells, full_width=full_width,
                deadline=deadline, stats=stats, table=table, ordering=ordering,
                use_tt=use_tt, use_ordering=use_ordering,
                endgame_full_width_cells=endgame_full_width_cells,
                tactical_extensions=tactical_extensions,
                tactical_growth=tactical_growth,
            )
        except SearchTimeout:
            stats.timed_out = True
            break
        if candidate is not None:
            best = candidate
            stats.completed_depth = depth
            if progress_callback is not None:
                total_counts = {name: getattr(stats, name) for name in last_counts}
                iteration_counts = {name: total_counts[name] - last_counts[name]
                                    for name in last_counts}
                last_counts = total_counts
                try:
                    progress_callback({
                        'kind': 'depth', 'depth': depth, 'best_turn': format_turn(best),
                        'evaluation': float(value),
                        'elapsed_seconds': round(time.monotonic() - iteration_started, 6),
                        'tt_size': len(table) if table is not None else 0,
                        'total': total_counts, 'iteration': iteration_counts,
                        'use_tt': use_tt, 'use_ordering': use_ordering,
                        'extension_limit': tactical_extensions,
                        'evaluation_variant': active_evaluation_variant(),
                    })
                except Exception:
                    pass  # Diagnostics must not fail an otherwise legal search.
        # Avoid launching another substantial iteration when almost no time
        # remains. The deadline still protects an unpredictable search cost.
        if time.monotonic() >= deadline:
            break
    return list(best)


def choose_move(state: GameState, time_budget_seconds: float) -> Turn:
    """Stable two-argument API used by GUI, tournament and existing tests."""
    caches = _SEARCH_CACHE.get()
    if caches is None:
        return iterative_deepening(state, time_budget_seconds, state.to_move)
    return iterative_deepening(
        state, time_budget_seconds, state.to_move,
        table=caches[0], ordering=caches[1],
    )
