"""Search-strength enhancements: correctness, cache safety and integration."""
import math
import time

import pytest

from experiments.phase6_common import build_position, fingerprint
from experiments.catchup_diagnostics import run_experiment
from src.board.board import WHITE, BLACK
from src.engine import search
from src.engine.evaluation import evaluate, position_features
from src.engine.move_generation import ranked_candidate_turns
from src.engine.player import AIPlayer
from src.engine.search import SearchStats, alpha_beta
from src.engine.transposition_table import TranspositionTable, position_key
from src.game.state import GameState


def test_small_branch_does_not_force_one_stone():
    state = GameState()
    state.apply_turn([(4, 5)])
    move = ranked_candidate_turns(state, max_branch=1)
    assert len(move) == 1 and 1 <= len(move[0]) <= 2
    state.apply_turn(move[0])


def test_candidate_diversity_when_budget_allows_each_size():
    state = GameState()
    state.apply_turn([(4, 5)])
    state.apply_turn([(0, 1), (8, 9)])
    state.apply_turn([(4, 4), (4, 6)])
    assert state.stones_allowed_this_turn() == 3
    moves = ranked_candidate_turns(state, max_branch=3)
    assert {len(turn) for turn in moves} == {1, 2, 3}


@pytest.mark.parametrize('empty', [3, 5, 7])
def test_automatic_exact_endgame_agrees_with_full_width(empty):
    state = build_position(500 + empty, empty)
    baseline = fingerprint(state)
    exact, _ = alpha_beta(state, 2, -math.inf, math.inf, state.to_move,
                          full_width=True, endgame_full_width_cells=0)
    stats = SearchStats()
    auto, turn = alpha_beta(state, 2, -math.inf, math.inf, state.to_move,
                            endgame_full_width_cells=7, stats=stats)
    assert auto == exact
    assert stats.endgame_full_width_nodes > 0
    assert fingerprint(state) == baseline
    state.apply_turn(turn)


def test_transposition_key_captures_threshold_config():
    state = build_position(15, 8)
    assert position_key(state, state.to_move, 12, 14, False,
                        endgame_full_width_cells=7) != position_key(
                        state, state.to_move, 12, 14, False,
                        endgame_full_width_cells=0)


def test_reused_table_has_root_hit_and_preserves_state():
    state = build_position(49, 7)
    baseline = fingerprint(state)
    table = TranspositionTable()
    score, _ = alpha_beta(state, 2, -math.inf, math.inf, state.to_move,
                          table=table)
    stats = SearchStats()
    repeat, _ = alpha_beta(state, 2, -math.inf, math.inf, state.to_move,
                           table=table, stats=stats)
    assert score == repeat
    assert stats.tt_hits > 0 and stats.tt_cutoffs > 0
    assert fingerprint(state) == baseline


def test_player_per_game_caches_are_distinct():
    w1, w2 = AIPlayer(WHITE, 3), AIPlayer(WHITE, 3)
    assert w1._table is not w2._table
    assert w1._ordering is not w2._ordering
    assert len(w1._table) == 0
    state = GameState()
    move = w1.choose_move(state)
    assert move and len(move) == 1
    assert len(w1._table) > 0 or w1.clock.time_left() < 3
    assert len(w2._table) == 0


def test_evaluation_components_and_antisymmetry():
    state = build_position(100, 12)
    features = position_features(state, state.to_move)
    assert features['largest'] >= 1
    assert features['best_growth'] >= 0
    assert evaluate(state, WHITE) == pytest.approx(-evaluate(state, BLACK))


def test_depth_five_legal_with_small_endgame():
    state = build_position(77, 2)
    before = fingerprint(state)
    stats = SearchStats()
    move = search.iterative_deepening(state, 1.2, state.to_move,
                                       max_depth=5, stats=stats)
    assert stats.completed_depth >= 4
    assert fingerprint(state) == before
    state.apply_turn(move)


def test_dashboard_can_decode_extended_key(tmp_path):
    report = run_experiment(4, seed=35, empty_cells=7,
                            max_depth=2, budget_seconds=2,
                            output_dir=tmp_path)
    assert report['iterations']
    assert report['tt_summary']['size'] > 0
    assert len(report['tt_preview']) > 0
