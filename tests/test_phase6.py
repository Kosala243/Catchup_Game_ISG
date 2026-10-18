"""Phase 6: complete-game invariants and experiment harness regression tests."""
import csv
import math
import random

import pytest

from src.board.board import WHITE, BLACK
from src.board.groups import group_sizes, largest_group_size
from src.engine.move_generation import legal_turns
from src.engine.search import SearchStats, alpha_beta
from src.game.state import GameState
from src.game.rules import compare_group_lists
from experiments.phase6_common import CONFIGS, build_position, fingerprint
from experiments.phase6_benchmark import benchmark
from experiments.phase6_matchups import play_game, run
from experiments.phase6_summary import summarize


@pytest.mark.parametrize("seed", [9, 17, 23, 41, 73])
def test_full_random_games_respect_rules_and_undo(seed):
    rng = random.Random(seed)
    state = GameState()
    seen = [fingerprint(state)]
    placements = 0
    while not state.is_game_over():
        mover = state.to_move
        allowed = state.stones_allowed_this_turn()
        empties = state.board.empty_cells()
        # Include all legal action sizes, rather than always taking the maximum.
        amount = rng.randint(1, min(allowed, len(empties)))
        move = rng.sample(empties, amount)
        state.apply_turn(move)
        placements += amount
        assert state.to_move != mover
        assert state.scores[mover] == largest_group_size(state.board, mover)
        assert state.scores[WHITE] >= 1 and state.scores[BLACK] >= 1
        assert len(state.board.empty_cells()) == 61 - placements
        seen.append(fingerprint(state))
    assert placements == 61
    actual = compare_group_lists(group_sizes(state.board, WHITE), group_sizes(state.board, BLACK))
    assert state.winner() == (WHITE if actual > 0 else BLACK if actual < 0 else None)
    with pytest.raises(ValueError):
        state.apply_turn([(4, 5)])
    for expected in reversed(seen[:-1]):
        state.undo()
        assert fingerprint(state) == expected
    assert not state.history and state.to_move == WHITE


@pytest.mark.parametrize("seed", [0, 2, 4])
def test_seeded_legal_position_is_reproducible(seed):
    a = build_position(seed, 9)
    b = build_position(seed, 9)
    assert fingerprint(a) == fingerprint(b)
    assert len(a.board.empty_cells()) == 9


def test_exact_full_width_agrees_with_brute_force_on_tiny_position():
    state = build_position(99, 3)
    before = fingerprint(state)
    perspective = state.to_move
    values = []
    for move in legal_turns(state):
        state.apply_turn(move)
        try:
            values.append(alpha_beta(state, 1, -math.inf, math.inf, perspective,
                                     full_width=True, use_tt=False, use_ordering=False)[0])
        finally:
            state.undo()
    exact = max(values)
    result, move = alpha_beta(state, 2, -math.inf, math.inf, perspective,
                              full_width=True)
    assert result == exact
    assert tuple(move) in {tuple(m) for m in legal_turns(state)}
    assert fingerprint(state) == before


def test_benchmark_writes_reproducible_rows_and_validates_state(tmp_path):
    destination = tmp_path / "benchmark.csv"
    rows = benchmark(depth=2, repeats=1, positions=((44, 5),), output=destination)
    assert len(rows) == len(CONFIGS)
    assert {r["configuration"] for r in rows} == {c.name for c in CONFIGS}
    assert all(r["same_value_as_baseline"] == 1 for r in rows)
    with destination.open(newline="", encoding="utf-8") as f:
        assert len(list(csv.DictReader(f))) == len(CONFIGS)


def test_paired_matchup_swaps_colours_and_opening(monkeypatch, tmp_path):
    # Deterministic testing only: don't spend real thinking time in a harness test.
    import experiments.phase6_matchups as matchups

    def first_legal(state, budget, colour, *, stats, **kwargs):
        stats.completed_depth = 1
        stats.nodes = 2
        return [state.board.empty_cells()[0]]

    monkeypatch.setattr(matchups, "iterative_deepening", first_legal)
    games, moves = run(pairs=1, budget_seconds=1.0, max_depth=2,
                       output_dir=tmp_path)
    assert len(games) == 2
    assert games[0]["white_config"] == games[1]["black_config"]
    assert games[0]["black_config"] == games[1]["white_config"]
    assert games[0]["opening"] == games[1]["opening"]
    assert all(row["termination"] == "board_full" for row in games)
    assert all(row["turns"] >= 2 for row in games)
    assert all(0 <= row["white_time_left"] <= 1.0 for row in games)
    assert all(0 <= row["black_time_left"] <= 1.0 for row in games)
    assert len(moves) == sum(row["turns"] - 1 for row in games)
    summary = summarize(tmp_path)
    assert "Paired games: 2 games" in summary


def test_illegal_search_move_is_reported_as_forfeit(monkeypatch):
    import experiments.phase6_matchups as matchups

    def invalid(state, budget, colour, *, stats, **kwargs):
        return [(20, 20)]

    monkeypatch.setattr(matchups, "iterative_deepening", invalid)
    a, b = CONFIGS[0], CONFIGS[-1]
    row, _ = play_game(1, 1, 2026, (4, 5), a, b, 1.0, 2)
    assert row["winner"] == WHITE  # Black is next after the forced White opening.