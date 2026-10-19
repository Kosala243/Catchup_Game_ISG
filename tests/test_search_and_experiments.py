"""Focused regression suite: search correctness, experiments, dashboard and packaging."""

# --- Exhaustive legal actions and evaluation ---
import sys
import math
import random
import pytest
import time
import csv
import json
import shutil
import zipfile
from threading import Event
from pathlib import Path

from src.board.board import BLACK, WHITE
from src.engine.evaluation import WIN_VALUE, evaluate, position_features
from src.engine.move_generation import legal_turns, ranked_candidate_turns, SearchTimeout
from src.engine.search import SearchStats, alpha_beta, choose_move, iterative_deepening
from src.game.state import GameState

from src.engine.move_ordering import MoveOrdering
from src.engine.transposition_table import (
    Bound, TTEntry, TranspositionTable, occupancy_bits, position_key, turn_mask,
)

from src.board.groups import group_sizes, largest_group_size
from src.game.rules import compare_group_lists
from experiments.lab import CONFIGS, build_position, fingerprint
from experiments.lab import benchmark
from experiments.lab import play_game, run_matchups as run
from experiments.lab import summarize

from experiments.lab import EXPERIMENTS, get_experiment, run_experiment
from src.engine import search
from src.engine.player import AIPlayer

from src.game.notation import parse_turn

from tools.build_release import collect_files, create_release, verify_release, REQUIRED_FILES
from tools.check_environment import check
from tools.windows_smoke import validate_result

from experiments.catchup_dashboard import (
    W, H, fit_viewport, initial_window_size, mouse_to_canvas
)

def _engine_fingerprint(state):
    return (tuple(state.board.cells.items()), tuple(state.scores.items()), state.to_move,
            state.is_opening_move, state.score_increased_last_turn,
            tuple((e.player, tuple(e.cells), tuple(e.scores_before.items()), e.opponent_score_increased_before)
                  for e in state.history))

def _engine_late_position(empties=4, seed=100):
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

@pytest.mark.parametrize('remaining', [1, 2, 3])
def test_full_width_alpha_beta_matches_brute_force(remaining):
    state = _engine_late_position(empties=remaining, seed=110 + remaining)
    before = _engine_fingerprint(state)
    expect = brute_force_minimax(state, depth=2, perspective=state.to_move)
    value, turn = alpha_beta(state, 2, -math.inf, math.inf, state.to_move, full_width=True)
    assert value == expect
    assert turn is not None
    assert tuple(turn) in {tuple(t) for t in legal_turns(state)}
    assert _engine_fingerprint(state) == before

def test_alpha_beta_from_opponents_perspective():
    state = _engine_late_position(empties=3, seed=1002)
    before = _engine_fingerprint(state)
    opponent = BLACK if state.to_move == WHITE else WHITE
    expect = brute_force_minimax(state, 2, opponent)
    actual, _ = alpha_beta(state, 2, -math.inf, math.inf, opponent, full_width=True)
    assert actual == expect
    assert _engine_fingerprint(state) == before

def test_evaluation_is_antisymmetric_nonterminal():
    state = GameState()
    for turn in [[(4, 5)], [(0, 5), (1, 5)], [(4, 4), (3, 4)]]:
        state.apply_turn(turn)
    assert evaluate(state, WHITE) == -evaluate(state, BLACK)

def test_selective_move_set_in_three_stone_position():
    state = GameState()
    state.apply_turn([(4, 5)])
    state.apply_turn([(0, 1), (8, 9)])
    state.apply_turn([(4, 4), (4, 6)])
    assert state.stones_allowed_this_turn() == 3
    choices = ranked_candidate_turns(state, max_branch=15)
    assert len(choices) == 15
    assert {len(c) for c in choices} == {1, 2, 3}
    assert len({tuple(c) for c in choices}) == len(choices)
    for turn in choices:
        before = _engine_fingerprint(state)
        state.apply_turn(turn)
        state.undo()
        assert _engine_fingerprint(state) == before

# --- Transposition keys, TT bounds, move ordering and exact search ---

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

# --- Full games, benchmarks and colour-swapped matches ---

@pytest.mark.parametrize("seed", [0, 2, 4])
def test_seeded_legal_position_is_reproducible(seed):
    a = build_position(seed, 9)
    b = build_position(seed, 9)
    assert fingerprint(a) == fingerprint(b)
    assert len(a.board.empty_cells()) == 9


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
    import experiments.lab as matchups

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
    import experiments.lab as matchups

    def invalid(state, budget, colour, *, stats, **kwargs):
        return [(20, 20)]

    monkeypatch.setattr(matchups, "iterative_deepening", invalid)
    a, b = CONFIGS[0], CONFIGS[-1]
    row, _ = play_game(1, 1, 2026, (4, 5), a, b, 1.0, 2)
    assert row["winner"] == WHITE  # Black is next after the forced White opening.


# --- Search-strength changes and endgame correctness ---

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

def test_dashboard_can_decode_extended_key(tmp_path):
    report = run_experiment(4, seed=35, empty_cells=7,
                            max_depth=2, budget_seconds=2,
                            output_dir=tmp_path)
    assert report['iterations']
    assert report['tt_summary']['size'] > 0
    assert len(report['tt_preview']) > 0

# --- Diagnostic dashboard trace and TT sampling ---

def demo(number, tmp_path, **kwargs):
    return run_experiment(number, seed=35, empty_cells=7, max_depth=2,
                          budget_seconds=3.0, output_dir=tmp_path, **kwargs)

def test_four_buttons_use_phase6_configs():
    assert [(e.number, e.configuration, e.use_tt, e.use_ordering)
            for e in EXPERIMENTS] == [
        (1, "baseline", False, False),
        (2, "ordering_only", False, True),
        (3, "tt_only", True, False),
        (4, "tt_and_ordering", True, True),
    ]
    with pytest.raises(ValueError):
        get_experiment(5)

@pytest.mark.parametrize("number", [1, 2, 3, 4])
def test_each_experiment_reports_real_depths_and_legal_turns(number, tmp_path):
    state = build_position(35, 7)
    original = fingerprint(state)
    events = []
    report = demo(number, tmp_path, on_event=events.append)
    assert fingerprint(state) == original
    assert [row["depth"] for row in report["iterations"]] == [1, 2]
    assert [row["completed_depth"] for row in report["iterations"]] == [1, 2]
    assert report["result"]["completed_depth"] == 2
    assert any(e["kind"] == "iteration" for e in events)
    for row in report["iterations"]:
        trial = state.copy()
        trial.apply_turn(parse_turn(row["best_turn"]))
        assert len(trial.history) == len(state.history) + 1
        assert row["nodes"] >= 1
        assert row["elapsed_seconds"] >= 0
    file = json.loads((tmp_path / __import__("pathlib").Path(report["saved_json"]).name).read_text())
    assert file["result"]["best_turn"] == report["result"]["best_turn"]
    with open(report["saved_csv"], newline="", encoding="utf-8") as stream:
        assert len(list(csv.DictReader(stream))) == 2

@pytest.mark.parametrize("number", [3, 4])
def test_tt_real_entries_and_bound_counts(number, tmp_path):
    r = demo(number, tmp_path)
    summary = r["tt_summary"]
    assert summary["size"] > 0
    assert summary["size"] == summary["exact"] + summary["lower"] + summary["upper"]
    assert summary["capacity"] == 50000
    assert len(r["tt_preview"]) <= 25
    for entry in r["tt_preview"]:
        assert entry["bound"] in ("exact", "lower", "upper")
        assert 0 <= entry["white_stones"] + entry["black_stones"] <= 61
        assert (int(entry["white_mask"], 16) & int(entry["black_mask"], 16)) == 0
        assert entry["to_move"] in ("W", "B")
        assert 1 <= entry["depth"] <= 2

@pytest.mark.parametrize("number", [1, 2])
def test_no_tt_is_truthfully_empty(number, tmp_path):
    r = demo(number, tmp_path)
    assert r["tt_summary"]["size"] == 0
    assert r["tt_preview"] == []
    assert all(row["tt_hits"] == 0 for row in r["iterations"])

def test_fixed_depth_values_agree_across_all_four_configs(tmp_path):
    values = []
    for number in range(1, 5):
        r = demo(number, tmp_path)
        values.append(r["iterations"][-1]["evaluation"])
    assert all(v == pytest.approx(values[0]) for v in values)

def test_cancel_before_begin_returns_legal_fallback(tmp_path):
    stop = Event()
    stop.set()
    r = demo(4, tmp_path, cancel=stop)
    assert r["iterations"] == []
    assert r["result"]["cancelled"]
    assert r["result"]["fallback_used"]
    state = build_position(35, 7)
    state.apply_turn(parse_turn(r["result"]["best_turn"]))

def test_zero_budget_is_not_falsely_reported_as_completed(tmp_path):
    r = run_experiment(4, seed=35, empty_cells=7, max_depth=3,
                       budget_seconds=0, output_dir=tmp_path)
    assert r["result"]["completed_depth"] == 0
    assert r["result"]["timed_out"]
    assert r["saved_csv"] is None

@pytest.mark.parametrize("options", [
    {"empty_cells": 0}, {"empty_cells": 61}, {"max_depth": 0},
    {"max_cells": 0}, {"max_branch": -1}, {"budget_seconds": float("nan")},
    {"tt_preview_limit": 101}, {"seed": "33"},
])
def test_reject_invalid_settings(options, tmp_path):
    defaults = dict(seed=35, empty_cells=7, max_depth=2,
                    budget_seconds=1, output_dir=tmp_path)
    defaults.update(options)
    with pytest.raises(ValueError):
        run_experiment(1, **defaults)

def test_dashboard_module_imports_without_pygame_at_module_import():
    from experiments.catchup_dashboard import main, run
    assert callable(run) and callable(main)

# --- Responsive window geometry and click mapping ---

def test_desktop_auto_sizes_leave_room_for_dock():
    assert initial_window_size((1440, 900)) == (1280, 740)
    assert initial_window_size((1280, 800)) == (1200, 640)
    assert initial_window_size((1920, 1080)) == (1280, 865)

@pytest.mark.parametrize("window_size", [(1280, 865), (1280, 740), (1000, 650), (720, 460), (1600, 900)])
def test_aspect_ratio_and_roundtrip(window_size):
    left, top, sw, sh = fit_viewport(window_size)
    assert 0 <= left and 0 <= top
    assert left + sw <= window_size[0] and top + sh <= window_size[1]
    assert abs(sw / sh - W / H) < 0.01
    for virtual in [(50, 90), (300, 200), (1000, 600), (640, 430), (1130, 750)]:
        point = (left + int((virtual[0] + 0.5) * sw / W),
                 top + int((virtual[1] + 0.5) * sh / H))
        mapped = mouse_to_canvas(point, window_size)
        assert mapped is not None
        # Pixel-quantization may shift a hit by about one virtual pixel.
        assert abs(mapped[0] - virtual[0]) <= 2
        assert abs(mapped[1] - virtual[1]) <= 2

def test_letterbox_click_does_not_activate_buttons():
    assert mouse_to_canvas((0, 0), (1600, 900)) is None
    assert mouse_to_canvas((1599, 899), (1600, 900)) is None

def test_bottom_bar_is_present_in_fit():
    window_size = (1000, 650)
    left, top, sw, sh = fit_viewport(window_size)
    # Physical location of bottom footer (virtual centre 850).
    pt = (left + sw // 2, top + int(850 * sh / H))
    hit = mouse_to_canvas(pt, window_size)
    assert hit is not None and 845 <= hit[1] <= 852

def test_invalid_sizes():
    with pytest.raises(ValueError):
        fit_viewport((1280, 0))
    with pytest.raises(ValueError):
        initial_window_size((0, 900))

# --- Release archive safety checks ---

@pytest.fixture
def tiny_project(tmp_path):
    root = tmp_path / "repo"
    for filename in REQUIRED_FILES:
        path = root / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {filename}\n", encoding="utf-8")
    (root / "src/engine/extra.py").write_text("pass\n", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests/dont_include.py").write_text("pass\n", encoding="utf-8")
    (root / "saves").mkdir()
    (root / "saves/current_game.json").write_text("{}", encoding="utf-8")
    return root

def test_release_contains_required_runtime_and_excludes_user_data(tiny_project, tmp_path):
    output = tmp_path / "output.zip"
    result, count = create_release(tiny_project, output)
    assert result == output.resolve()
    assert count == len(collect_files(tiny_project))
    assert verify_release(output) == count
    with zipfile.ZipFile(output) as z:
        paths = set(z.namelist())
        assert "Catchup/run.bat" in paths
        assert "Catchup/src/engine/extra.py" in paths
        assert "Catchup/SHA256SUMS.txt" in paths
        assert not any("saves/" in p or "tests/" in p for p in paths)

def test_missing_critical_file_rejected(tiny_project, tmp_path):
    (tiny_project / "src/engine/search.py").unlink()
    with pytest.raises(FileNotFoundError):
        create_release(tiny_project, tmp_path / "bad.zip")

def test_tampering_with_zip_is_detected(tiny_project, tmp_path):
    good = tmp_path / "good.zip"
    bad = tmp_path / "bad.zip"
    create_release(tiny_project, good)
    with zipfile.ZipFile(good) as source, zipfile.ZipFile(bad, "w") as dest:
        for member in source.namelist():
            data = source.read(member)
            if member == "Catchup/main.py":
                data = b"tampered contents\n"
            dest.writestr(member, data)
    with pytest.raises(ValueError, match="Checksum mismatch"):
        verify_release(bad)

def test_unsafe_or_unlisted_files_excluded(tiny_project):
    (tiny_project / "experiments").mkdir()
    (tiny_project / "experiments/results.csv").write_text("private data")
    (tiny_project / "src/game/test_notes.txt").parent.mkdir(parents=True, exist_ok=True)
    (tiny_project / "src/game/test_notes.txt").write_text("private data")
    rel = {p.relative_to(tiny_project).as_posix() for p in collect_files(tiny_project)}
    assert "experiments/results.csv" not in rel
    assert "src/game/test_notes.txt" not in rel

def test_result_parser_accepts_finished_game():
    output = "{'winner': 'W', 'final_scores': {'W': 30, 'B': 19}, 'turns': 26, 'white_time_left': 596.0, 'black_time_left': 597.0}\n"
    result = validate_result(output)
    assert result["winner"] == "W" and result["turns"] == 26

# --- End-to-end checks of consolidated experiment entrypoints ---

def test_strength_comparison_uses_swapped_colours_and_finishes(tmp_path):
    from experiments.lab import run_strength
    path = tmp_path / 'strength.csv'
    games = run_strength(pairs=1, seconds=1.0, seed_start=2001, output=str(path))
    assert len(games) == 2
    assert games[0]['white_profile'] == games[1]['black_profile']
    assert games[0]['black_profile'] == games[1]['white_profile']
    assert games[0]['seed'] == games[1]['seed'] == 2001
    assert all(g['termination'] == 'board_full' for g in games)
    assert path.is_file()

def test_consolidated_cli_help_is_executable():
    import subprocess
    import sys
    completed = subprocess.run([sys.executable, '-m', 'experiments.lab', '--help'],
                               capture_output=True, text=True, timeout=10, check=True)
    assert all(cmd in completed.stdout for cmd in ('trace', 'benchmark', 'matchups', 'strength', 'summary', 'plots'))

def test_consolidated_plotter_uses_actual_benchmark_data(tmp_path):
    pytest.importorskip('matplotlib')
    from experiments.lab import benchmark, plot
    benchmark(depth=1, repeats=1, positions=((35, 7),), output=tmp_path/'phase6_benchmark.csv')
    generated = plot(tmp_path)
    assert len(generated) == 2
    assert all(path.is_file() and path.stat().st_size > 1000 for path in generated)