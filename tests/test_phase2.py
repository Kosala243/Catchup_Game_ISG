"""Phase 2 correctness tests for exhaustive turns and exact-depth alpha-beta."""
import math
import random
import time

import pytest

from src.board.board import BLACK, WHITE
from src.engine.evaluation import WIN_VALUE, evaluate
from src.engine.move_generation import legal_turns, ranked_candidate_turns, SearchTimeout
from src.engine.search import SearchStats, alpha_beta, choose_move, iterative_deepening
from src.game.state import GameState


def fingerprint(state):
    return (tuple(state.board.cells.items()), tuple(state.scores.items()), state.to_move,
            state.is_opening_move, state.score_increased_last_turn,
            tuple((e.player, tuple(e.cells), tuple(e.scores_before.items()), e.opponent_score_increased_before)
                  for e in state.history))


def late_position(empties=4, seed=100):
    rng = random.Random(seed)
    state = GameState()
    while len(state.board.empty_cells()) > empties:
        vacant = state.board.empty_cells()
        max_allowed = min(state.stones_allowed_this_turn(), len(vacant))
        count = min(max_allowed, len(vacant) - empties)
        if count == 0:
            break
        state.apply_turn(rng.sample(vacant, count))
    assert len(state.board.empty_cells()) == empties
    return state


def brute_force_minimax(state, depth, perspective):
    if depth == 0 or state.is_game_over():
        return evaluate(state, perspective)
    maximizing = state.to_move == perspective
    values = []
    for move in legal_turns(state):
        state.apply_turn(move)
        try:
            values.append(brute_force_minimax(state, depth - 1, perspective))
        finally:
            state.undo()
    return (max(values) if maximizing else min(values))


def test_exact_61_openings_and_does_not_mutate():
    state = GameState()
    before = fingerprint(state)
    moves = list(legal_turns(state))
    assert len(moves) == 61
    assert all(len(t) == 1 for t in moves)
    assert fingerprint(state) == before


def test_black_first_turn_exact_count():
    state = GameState()
    state.apply_turn([(4, 5)])
    moves = list(legal_turns(state))
    assert len(moves) == 60 + math.comb(60, 2) == 1830
    assert len(set(tuple(t) for t in moves)) == len(moves)


def test_three_stone_turn_counts_all_sizes():
    state = GameState()
    state.apply_turn([(4, 5)])  # White opening; Black may NOT use 3 stones.
    assert state.stones_allowed_this_turn() == 2
    state.apply_turn([(0, 1), (8, 9)])  # Black largest group still 1.
    state.apply_turn([(4, 4), (4, 6)])  # White grows from 1 to 3.
    assert state.to_move == BLACK
    assert state.stones_allowed_this_turn() == 3
    n = len(state.board.empty_cells())
    assert len(list(legal_turns(state))) == n + math.comb(n, 2) + math.comb(n, 3)


def test_candidates_all_legal_and_distinct():
    state = GameState()
    state.apply_turn([(4, 5)])
    before = fingerprint(state)
    generated = ranked_candidate_turns(state, max_branch=12)
    exact = {tuple(t) for t in legal_turns(state)}
    assert generated
    assert len(generated) == len({tuple(t) for t in generated})
    assert all(tuple(t) in exact for t in generated)
    assert {len(t) for t in generated} == {1, 2}
    assert fingerprint(state) == before


def test_terminal_tiebreak_used_in_evaluator():
    state = late_position(empties=1)
    assert not state.is_game_over()
    state.apply_turn([state.board.empty_cells()[0]])
    assert state.is_game_over()
    winner = state.winner()
    if winner is None:
        assert evaluate(state, WHITE) == 0.0
        assert evaluate(state, BLACK) == 0.0
    else:
        loser = BLACK if winner == WHITE else WHITE
        assert evaluate(state, winner) == WIN_VALUE
        assert evaluate(state, loser) == -WIN_VALUE


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_alpha_beta_matches_brute_force_on_small_positions(seed):
    """The one check that actually exercises the real search function: full-width
    alpha-beta must agree exactly with an independently-written plain minimax
    (no pruning, no move restriction) over the same exhaustive move set."""
    state = late_position(empties=4, seed=seed)
    colour = state.to_move
    before = fingerprint(state)

    exact_value, exact_move = alpha_beta(state, 2, -math.inf, math.inf, colour, full_width=True)
    assert fingerprint(state) == before  # alpha_beta must restore state even on success

    brute_value = brute_force_minimax(state, 2, colour)
    assert exact_value == pytest.approx(brute_value)

    if exact_move is not None:
        assert tuple(exact_move) in {tuple(t) for t in legal_turns(state)}


def test_immediate_timeout_raises_and_leaves_state_untouched():
    state = late_position(empties=6, seed=5)
    colour = state.to_move
    before = fingerprint(state)
    expired_deadline = time.monotonic() - 1.0
    with pytest.raises(SearchTimeout):
        alpha_beta(state, 3, -math.inf, math.inf, colour, deadline=expired_deadline)
    assert fingerprint(state) == before


def test_timeout_mid_search_restores_state_exactly():
    # Large enough (full-width, 7 empties, depth 4) that a 10ms deadline is
    # certain to fire partway through, not just at the very first check.
    state = late_position(empties=7, seed=11)
    colour = state.to_move
    before = fingerprint(state)
    deadline = time.monotonic() + 0.01
    with pytest.raises(SearchTimeout):
        alpha_beta(state, 4, -math.inf, math.inf, colour, full_width=True, deadline=deadline)
    assert fingerprint(state) == before


def test_choose_move_is_legal_and_nonmutating_from_a_midgame_state():
    state = late_position(empties=10, seed=21)
    before = fingerprint(state)
    move = choose_move(state, time_budget_seconds=0.3)
    assert fingerprint(state) == before
    assert 1 <= len(move) <= state.stones_allowed_this_turn()
    assert len(set(move)) == len(move)
    assert set(move).issubset(set(state.board.empty_cells()))


def test_iterative_deepening_reports_stats():
    state = late_position(empties=8, seed=42)
    colour = state.to_move
    stats = SearchStats()
    move = iterative_deepening(state, 0.3, colour, max_depth=3, stats=stats)
    assert 1 <= len(move) <= state.stones_allowed_this_turn()
    assert stats.nodes > 0
    assert stats.leaves > 0
    assert stats.completed_depth >= 1