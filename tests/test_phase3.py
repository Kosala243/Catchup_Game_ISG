"""Phase 3 regression tests: exact keys, TT bounds, ordering and interruption."""
import math
import random
import time

import pytest

from src.board.board import WHITE, BLACK
from src.engine.evaluation import evaluate
from src.engine.move_generation import SearchTimeout, legal_turns, ranked_candidate_turns
from src.engine.move_ordering import MoveOrdering
from src.engine.search import SearchStats, alpha_beta, iterative_deepening
from src.engine.transposition_table import (
    Bound, TTEntry, TranspositionTable, occupancy_bits, position_key, turn_mask,
)
from src.game.state import GameState


def state_snapshot(s):
    return (tuple(s.board.cells.items()), tuple(s.scores.items()), s.to_move,
            s.score_increased_last_turn, s.is_opening_move,
            tuple((h.player, tuple(h.cells), tuple(h.scores_before.items()),
                   h.opponent_score_increased_before) for h in s.history))


def position(empties=4, seed=25):
    rng = random.Random(seed)
    s = GameState()
    while len(s.board.empty_cells()) > empties:
        vacancies = s.board.empty_cells()
        count = min(s.stones_allowed_this_turn(), len(vacancies) - empties)
        s.apply_turn(rng.sample(vacancies, count))
    return s


def brute(s, depth, perspective):
    if not depth or s.is_game_over():
        return evaluate(s, perspective)
    values = []
    for action in legal_turns(s):
        s.apply_turn(action)
        try:
            values.append(brute(s, depth - 1, perspective))
        finally:
            s.undo()
    return (max if s.to_move == perspective else min)(values)


def test_bitboards_cover_board_exactly():
    s = position(3)
    white, black = occupancy_bits(s)
    assert white & black == 0
    assert white.bit_count() == len(s.board.stones_of(WHITE))
    assert black.bit_count() == len(s.board.stones_of(BLACK))
    assert (white | black).bit_count() == 58


def test_incremental_masks_and_undo():
    s = position(6)
    snapshot = state_snapshot(s)
    white, black = occupancy_bits(s)
    action = next(legal_turns(s))
    mask = turn_mask(action)
    mover = s.to_move
    s.apply_turn(action)
    expected = (white | mask, black) if mover == WHITE else (white, black | mask)
    assert occupancy_bits(s) == expected
    s.undo()
    assert state_snapshot(s) == snapshot


def test_position_key_all_rule_dimensions():
    s = GameState()
    baseline = position_key(s, WHITE, 12, 14, False)
    for perspective, width, cells, full in [(BLACK, 12, 14, False),
                                            (WHITE, 13, 14, False),
                                            (WHITE, 12, 15, False),
                                            (WHITE, 12, 14, True)]:
        assert position_key(s, perspective, width, cells, full) != baseline
    copy = s.copy()
    copy.score_increased_last_turn = True
    assert position_key(copy, WHITE, 12, 14, False) != baseline
    copy = s.copy()
    copy.to_move = BLACK
    assert position_key(copy, WHITE, 12, 14, False) != baseline
    copy = s.copy()
    copy.is_opening_move = False
    assert position_key(copy, WHITE, 12, 14, False) != baseline
    copy = s.copy()
    copy.scores[WHITE] = 2
    assert position_key(copy, WHITE, 12, 14, False) != baseline


def test_key_identical_for_transposed_turn_orders():
    a, b = GameState(), GameState()
    a.apply_turn([(4, 5)])
    b.apply_turn([(4, 5)])
    a.apply_turn([(0, 1), (1, 1)])
    b.apply_turn([(1, 1), (0, 1)])
    assert state_snapshot(a) != state_snapshot(b)  # history preserves action order
    assert position_key(a, WHITE, 12, 14, False) == position_key(b, WHITE, 12, 14, False)


def test_table_replacement_and_bounded_capacity():
    t = TranspositionTable(max_entries=2)
    first, second, third = ('a',), ('b',), ('c',)
    t.store(first, TTEntry(3, 5.0, Bound.EXACT, None))
    assert not t.store(first, TTEntry(2, 7.0, Bound.EXACT, None))
    assert not t.store(first, TTEntry(3, 8.0, Bound.LOWER, None))
    assert t.get(first).value == 5.0
    t.store(second, TTEntry(1, 2.0, Bound.UPPER, None))
    t.store(third, TTEntry(1, 3.0, Bound.EXACT, None))
    assert len(t) == 2 and t.get(first) is None
    assert t.get(second) is not None and t.get(third) is not None
    with pytest.raises(ValueError):
        TranspositionTable(max_entries=0)


def test_move_ordering_preserves_action_set_and_pv_first():
    s = position(6)
    moves = ranked_candidate_turns(s, max_branch=10)
    ordered = MoveOrdering()
    last = tuple(moves[-1])
    result = ordered.order_moves(moves, s.to_move, 2, pv_move=last)
    assert tuple(result[0]) == last
    assert {tuple(m) for m in result} == {tuple(m) for m in moves}
    assert len(result) == len(moves)


def test_cutoff_history_promotes_without_overriding_strong_priorities():
    s = position(6)
    moves = ranked_candidate_turns(s, max_branch=8)
    ordering = MoveOrdering()
    target = moves[-1]
    ordering.record_cutoff(s.to_move, 2, target)
    result = ordering.order_moves(moves, s.to_move, 2)
    assert result.index(target) < moves.index(target)
    assert {tuple(m) for m in result} == {tuple(m) for m in moves}


@pytest.mark.parametrize('seed', [10, 11, 12, 13, 14])
def test_full_width_matches_exhaustive_minimax_with_ttable(seed):
    s = position(3, seed=seed)
    initial = state_snapshot(s)
    expected = brute(s, 2, s.to_move)
    stats = SearchStats()
    actual, action = alpha_beta(s, 2, -math.inf, math.inf, s.to_move,
                                full_width=True, stats=stats)
    assert actual == expected
    assert tuple(action) in {tuple(a) for a in legal_turns(s)}
    assert stats.tt_stores > 0
    assert state_snapshot(s) == initial


@pytest.mark.parametrize('perspective', [WHITE, BLACK])
def test_full_width_both_perspectives(perspective):
    s = position(3, seed=35)
    expected = brute(s, 2, perspective)
    actual, _ = alpha_beta(s, 2, -math.inf, math.inf, perspective, full_width=True)
    assert actual == expected


def test_table_hit_on_repeated_search():
    s = position(5, seed=18)
    table = TranspositionTable()
    first, _ = alpha_beta(s, 2, -math.inf, math.inf, s.to_move,
                          full_width=True, table=table)
    stats = SearchStats()
    second, _ = alpha_beta(s, 2, -math.inf, math.inf, s.to_move,
                           full_width=True, table=table, stats=stats)
    assert second == first
    assert stats.tt_hits >= 1 and stats.tt_cutoffs >= 1


def test_no_tt_no_ordering_same_exact_value():
    s = position(4, seed=38)
    initial = state_snapshot(s)
    on, _ = alpha_beta(s, 2, -math.inf, math.inf, s.to_move, full_width=True)
    off, _ = alpha_beta(s, 2, -math.inf, math.inf, s.to_move, full_width=True,
                        use_tt=False, use_ordering=False)
    assert on == off
    assert state_snapshot(s) == initial


def test_reused_table_separates_opposite_perspectives():
    s = position(4, seed=39)
    table = TranspositionTable()
    first, _ = alpha_beta(s, 2, -math.inf, math.inf, WHITE, full_width=True, table=table)
    second, _ = alpha_beta(s, 2, -math.inf, math.inf, BLACK, full_width=True, table=table)
    assert first == -second


def test_timeout_restores_board_and_history(monkeypatch):
    import src.engine.search as search
    s = GameState()
    baseline = state_snapshot(s)
    count = [0]
    def raise_after(deadline):
        count[0] += 1
        if count[0] == 4:
            raise SearchTimeout()
    monkeypatch.setattr(search, 'check_deadline', raise_after)
    with pytest.raises(SearchTimeout):
        alpha_beta(s, 3, -math.inf, math.inf, WHITE)
    assert state_snapshot(s) == baseline


def test_zero_time_returns_legal_fallback_without_state_change():
    s = GameState()
    baseline = state_snapshot(s)
    stats = SearchStats()
    chosen = iterative_deepening(s, 0.0, s.to_move, stats=stats)
    assert len(chosen) == 1
    assert stats.timed_out and stats.completed_depth == 0
    assert state_snapshot(s) == baseline


def test_early_move_with_tight_budget_is_legal():
    s = GameState()
    start = time.monotonic()
    chosen = iterative_deepening(s, 0.04, WHITE)
    assert time.monotonic() - start < 1.0  # generous for shared CI
    s.apply_turn(chosen)