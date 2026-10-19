"""Testing: Catchup rules, clocks, modes and persistence."""

# Board geometry, opening rules, groups, state, undo
import json
import random
import pytest
import math
import time
import sys
import csv
from threading import Event

from src.board.board import BLACK, WHITE, Board
from src.board.coordinates import (
    all_cells, col_bounds, from_notation, is_valid, neighbours, to_notation
)
from src.board.groups import group_sizes, largest_group_size
from src.game.notation import format_turn, parse_turn
from src.game.rules import compare_group_lists, max_stones_allowed
from src.game.state import GameState
from src.persistence.save_load import _state_to_dict, load_game, save_game, save_tournament_session, load_tournament_session

from src.engine.evaluation import WIN_VALUE, evaluate
from src.engine.move_generation import legal_turns, ranked_candidate_turns, SearchTimeout
from src.engine.search import SearchStats, alpha_beta, choose_move, iterative_deepening

from src.engine.player import AIPlayer
from src.engine.time_manager import Clock, allocate_time
from src.engine import search
from src.modes import tournament_mode

from src.gui.ai_worker import AIWorker
from src.modes.human_vs_ai import HumanGameController
from src.modes.self_play import VisualSelfPlayController
from src.modes.tournament_mode import undo_last_exchange

from experiments.lab import CONFIGS, build_position, fingerprint
from experiments.lab import benchmark
from experiments.lab import play_game, run_matchups as run
from experiments.lab import summarize

def notation(*names):
    return [from_notation(name) for name in names]

def test_board_shape_and_labelled_rows():
    cells = list(all_cells())
    assert len(cells) == 61
    assert len(set(cells)) == 61
    assert [col_bounds(row)[1] - col_bounds(row)[0] + 1 for row in range(1, 10)] == [5, 6, 7, 8, 9, 8, 7, 6, 5]
    for labels in ("A1 E1", "A5 I5", "E9 I9"):
        assert all(is_valid(cell) for cell in notation(*labels.split()))
    for cell in cells:
        assert from_notation(to_notation(cell)) == cell

def test_neighbour_geometry_reciprocal_and_six_corners():
    cells = set(all_cells())
    edges = set()
    degrees = []
    for cell in cells:
        adjacent = list(neighbours(cell))
        degrees.append(len(adjacent))
        assert len(adjacent) == len(set(adjacent))
        assert all(n in cells and cell in set(neighbours(n)) for n in adjacent)
        edges.update(frozenset((cell, n)) for n in adjacent)
    assert degrees.count(3) == 6
    assert len(edges) == 156
    assert set(neighbours(from_notation("E5"))) == set(notation("F6", "F5", "E4", "D4", "D5", "E6"))

@pytest.mark.parametrize("bad", ["", "A", "J5", "I1", "A9", "A0", "A10", "E-1", "5E", "  "])
def test_invalid_notation_rejected(bad):
    with pytest.raises(ValueError):
        from_notation(bad)

def test_groups_have_expected_connected_sizes():
    board = Board()
    for cell in notation("E5", "F5", "F6", "D1", "I9"):
        board.place(cell, WHITE)
    for cell in notation("B5", "C5"):
        board.place(cell, BLACK)
    assert group_sizes(board, WHITE) == [3, 1, 1]
    assert largest_group_size(board, WHITE) == 3
    assert group_sizes(board, BLACK) == [2]
    assert group_sizes(Board(), WHITE) == []

def test_opening_and_catchup_bonus_from_full_game_state():
    state = GameState()
    assert state.stones_allowed_this_turn() == 1
    assert state.scores == {WHITE: 1, BLACK: 1}
    state.apply_turn(notation("E5"))
    assert state.to_move == BLACK
    assert state.stones_allowed_this_turn() == 2  # special opening exception
    assert not state.score_increased_last_turn
    state.apply_turn(notation("B5", "C5"))
    assert state.scores[BLACK] == 2
    assert state.score_increased_last_turn
    assert state.stones_allowed_this_turn() == 3
    state.apply_turn(notation("D5", "E6", "F6"))
    assert state.scores[WHITE] == 4
    assert state.score_increased_last_turn
    assert state.stones_allowed_this_turn() == 3

def test_no_bonus_if_opponent_did_not_increase_or_still_behind():
    state = GameState()
    state.apply_turn(notation("E5"))
    state.apply_turn(notation("A1", "I9"))
    assert state.stones_allowed_this_turn() == 2
    assert max_stones_allowed(mover_score=5, opponent_score=4, opponent_score_increased=True) == 2
    assert max_stones_allowed(mover_score=5, opponent_score=5, opponent_score_increased=True) == 3
    assert max_stones_allowed(mover_score=5, opponent_score=7, opponent_score_increased=False) == 2

def test_tie_break_uses_all_groups_and_multiplicity():
    assert compare_group_lists([6, 5, 5, 3], [6, 5, 4, 3]) == 1
    assert compare_group_lists([3, 2, 2], [3, 2, 3]) == -1
    assert compare_group_lists([3, 2], [3, 2, 1]) == -1
    assert compare_group_lists([2, 2, 1], [1, 2, 2]) == 0
    assert compare_group_lists([], []) == 0

def test_failed_multicell_turn_is_fully_atomic():
    state = GameState()
    state.apply_turn(notation("E5"))
    before = _state_to_dict(state)
    invalid_turns = [
        notation("A1", "E5"),        # occupied *second* cell
        [from_notation("A1"), (8, 1)],  # invalid *second* cell
        notation("A1", "A1"),
        notation("A1", "B1", "C1"),   # first Black turn cannot take 3
        [],
    ]
    for turn in invalid_turns:
        with pytest.raises(ValueError):
            state.apply_turn(turn)
        assert _state_to_dict(state) == before

def test_copy_is_independent_and_undo_recovers_pre_move_state():
    state = GameState()
    state.apply_turn(notation("E5"))
    state.apply_turn(notation("B5", "C5"))
    expected = _state_to_dict(state)
    cloned = state.copy()
    assert _state_to_dict(cloned) == expected
    cloned.apply_turn(notation("D5", "E6", "F6"))
    assert _state_to_dict(state) == expected
    cloned.undo()
    assert _state_to_dict(cloned) == expected
    cloned.history[-1].cells.append(from_notation("A1"))
    cloned.history[-1].scores_before[WHITE] = 99
    assert _state_to_dict(state) == expected

def test_save_load_preserves_bonuses_undo_and_history(tmp_path):
    state = GameState()
    state.apply_turn(notation("E5"))
    state.apply_turn(notation("B5", "C5"))
    assert state.stones_allowed_this_turn() == 3
    path = tmp_path / "nested" / "autosave.json"
    save_game(state, str(path))
    restored = load_game(str(path))
    assert _state_to_dict(restored) == _state_to_dict(state)
    assert restored.stones_allowed_this_turn() == 3
    restored.apply_turn(notation("D5", "E6", "F6"))
    restored.undo()
    assert _state_to_dict(restored) == _state_to_dict(state)
    restored.undo()
    state.undo()
    assert _state_to_dict(restored) == _state_to_dict(state)

def test_load_rejects_corrupt_or_inconsistent_saves(tmp_path):
    state = GameState()
    state.apply_turn(notation("E5"))
    path = tmp_path / "game.json"
    save_game(state, str(path))
    for key, change in (
        ("scores", lambda d: d["scores"].update({"W": 50})),
        ("cells", lambda d: d["cells"].pop()),
        ("history", lambda d: d["history"][0]["cells"].append([1, 1])),
    ):
        data = json.loads(path.read_text(encoding="utf8"))
        change(data)
        path.write_text(json.dumps(data), encoding="utf8")
        with pytest.raises(ValueError):
            load_game(str(path))
        save_game(state, str(path))

def test_random_complete_games_and_full_undo():
    rng = random.Random(20261016)
    for _ in range(12):
        state = GameState()
        snapshots = [_state_to_dict(state)]
        while not state.is_game_over():
            empties = state.legal_cell_choices()
            number = rng.randint(1, min(len(empties), state.stones_allowed_this_turn()))
            mover = state.to_move
            state.apply_turn(rng.sample(empties, number))
            assert state.scores[mover] == max(1, largest_group_size(state.board, mover))
            assert state.score_increased_last_turn == (
                state.scores[mover] > state.history[-1].scores_before[mover]
            )
            snapshots.append(_state_to_dict(state))
        assert sum(value is not None for value in state.board.cells.values()) == 61
        assert state.winner() in (WHITE, BLACK, None)
        with pytest.raises(ValueError):
            state.apply_turn([from_notation("A1")])
        for snapshot in reversed(snapshots[:-1]):
            state.undo()
            assert _state_to_dict(state) == snapshot
        with pytest.raises(IndexError):
            state.undo()

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

def test_exact_61_openings_and_does_not_mutate():
    state = GameState()
    before = _engine_fingerprint(state)
    moves = list(legal_turns(state))
    assert len(moves) == 61
    assert all(len(t) == 1 for t in moves)
    assert _engine_fingerprint(state) == before

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

def test_terminal_tiebreak_used_in_evaluator():
    state = _engine_late_position(empties=1)
    assert not state.is_game_over()
    state.apply_turn([state.board.empty_cells()[0]])
    assert state.is_game_over()
    winner = state.winner()
    expected = 0.0 if winner is None else WIN_VALUE if winner == WHITE else -WIN_VALUE
    assert evaluate(state, WHITE) == expected
    assert evaluate(state, WHITE) == -evaluate(state, BLACK)

def test_timeout_inside_recursion_still_undoes(monkeypatch):
    import src.engine.search as search_module
    state = GameState()
    before = _engine_fingerprint(state)
    calls = [0]
    def interrupt_after_first_placement(deadline):
        calls[0] += 1
        if calls[0] >= 3:
            raise SearchTimeout()
    monkeypatch.setattr(search_module, "check_deadline", interrupt_after_first_placement)
    with pytest.raises(SearchTimeout):
        alpha_beta(state, 3, -math.inf, math.inf, WHITE)
    assert _engine_fingerprint(state) == before

# Whole-game clocks, autosave and restart safety

class FakeTime:
    def __init__(self, value=1000.0):
        self.value = value

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds

def _clock_state_snapshot(s):
    return (tuple(s.board.cells.items()), tuple(s.scores.items()), s.to_move,
            s.score_increased_last_turn, s.is_opening_move,
            tuple((e.player, tuple(e.cells), tuple(e.scores_before.items()),
                   e.opponent_score_increased_before) for e in s.history))

def test_clock_starts_at_correct_budget_and_only_charges_thinking():
    t = FakeTime()
    clock = Clock(total_seconds=600, time_source=t)
    t.advance(700)
    assert clock.time_left() == 600
    clock.start_move()
    t.advance(1.25)
    assert clock.time_left() == pytest.approx(598.75)
    assert clock.stop_move() == pytest.approx(1.25)
    t.advance(999)
    assert clock.time_left() == pytest.approx(598.75)

def test_clock_multiple_turns_clamps_to_zero_without_double_charging():
    t = FakeTime()
    clock = Clock(3.0, time_source=t)
    clock.start_move()
    t.advance(2.5)
    assert clock.stop_move() == 2.5
    assert clock.stop_move() == 0.0
    assert clock.time_left() == 0.5
    clock.start_move()
    t.advance(3.0)
    clock.stop_move()
    assert clock.time_left() == 0
    with pytest.raises(TimeoutError):
        clock.start_move()

def test_clock_rejects_invalid_construction():
    for value in (float('nan'), float('inf'), -3, 0, True):
        with pytest.raises(ValueError):
            Clock(total_seconds=value)
    with pytest.raises(ValueError):
        Clock(50, remaining_seconds=60)
    with pytest.raises(ValueError):
        Clock(50, remaining_seconds=-1)

def test_clock_rejects_double_start():
    clock = Clock(100)
    clock.start_move()
    with pytest.raises(RuntimeError):
        clock.start_move()
    clock.stop_move()

@pytest.mark.parametrize('time_left,moves', [
    (600.0, 20), (40.0, 8), (5.0, 2), (0.01, 1), (0.0, 1)
])
def test_time_budget_nonnegative_and_below_remaining(time_left, moves):
    budget = allocate_time(time_left, moves)
    assert 0 <= budget <= time_left
    if time_left > 0:
        assert budget < time_left

def test_player_clock_stops_even_when_search_raises(monkeypatch):
    state = GameState()
    player = AIPlayer(WHITE, 30)
    t = FakeTime()
    player.clock = Clock(30, time_source=t)

    def bad_search(*args):
        t.advance(3.0)
        raise RuntimeError('synthetic search error')

    monkeypatch.setattr(search, 'choose_move', bad_search)
    with pytest.raises(RuntimeError, match='synthetic'):
        player.choose_move(state)
    assert player.clock.time_left() == 27.0
    assert not player.clock.is_running

def test_tournament_session_restores_board_history_and_remaining_time(tmp_path):
    state = GameState()
    state.apply_turn([(4, 5)])
    state.apply_turn([(0, 1), (1, 1)])
    before = _clock_state_snapshot(state)
    clock = Clock(total_seconds=600, remaining_seconds=153.25)
    path = tmp_path / 'session.json'
    save_tournament_session(state, str(path), WHITE, clock)
    restored, restored_clock = load_tournament_session(str(path), WHITE)
    assert _clock_state_snapshot(restored) == before
    assert restored_clock.time_left() == 153.25
    restored.undo()
    assert len(restored.history) == 1
    assert len(state.history) == 2

def test_tournament_crash_reservation_charged_exactly_once(tmp_path):
    path = str(tmp_path / 'session.json')
    state = GameState()
    clock = Clock(100, remaining_seconds=70)
    save_tournament_session(state, path, WHITE, clock, reserved_seconds=12.5)
    loaded, recovered = load_tournament_session(path, WHITE, max_total_seconds=100)
    assert recovered.time_left() == 57.5
    save_tournament_session(loaded, path, WHITE, recovered)
    _, loaded_again = load_tournament_session(path, WHITE, max_total_seconds=100)
    assert loaded_again.time_left() == 57.5

def test_plain_game_save_remains_backward_compatible(tmp_path):
    state = GameState()
    state.apply_turn([(4, 5)])
    path = str(tmp_path / 'legacy.json')
    save_game(state, path)
    assert _clock_state_snapshot(load_game(path)) == _clock_state_snapshot(state)
    with pytest.raises(ValueError, match='no tournament clock'):
        load_tournament_session(path, WHITE)

def test_resume_wrong_colour_is_rejected(tmp_path):
    path = str(tmp_path / 'session.json')
    save_tournament_session(GameState(), path, WHITE, Clock(600))
    with pytest.raises(ValueError, match='colour'):
        load_tournament_session(path, BLACK)

@pytest.mark.parametrize('field,value', [
    ('remaining_seconds', 999),
    ('reserved_seconds', 999),
    ('remaining_seconds', -1),
    ('total_seconds', 601),
    ('remaining_seconds', float('nan')),
    ('remaining_seconds', '90'),
])
def test_malformed_or_inflated_saved_clock_rejected(tmp_path, field, value):
    path = str(tmp_path / 'session.json')
    save_tournament_session(GameState(), path, WHITE, Clock(600))
    data = json.loads(open(path).read())
    data['clock'][field] = value
    open(path, 'w').write(json.dumps(data))
    with pytest.raises(ValueError):
        load_tournament_session(path, WHITE)

def test_tournament_autosave_and_resume_integration(tmp_path, monkeypatch):
    """Start as Black, type White opening, then stop at next prompt and resume."""
    path = str(tmp_path / 'current_game.json')
    monkeypatch.setattr(tournament_mode, 'AUTOSAVE_PATH', path)

    def instant_search(state, budget):
        return [state.board.empty_cells()[0]]
    monkeypatch.setattr(search, 'choose_move', instant_search)
    inputs = iter(['E5'])

    def controlled_input(prompt):
        return next(inputs)
    monkeypatch.setattr('builtins.input', controlled_input)
    with pytest.raises(StopIteration):
        tournament_mode.run(BLACK, think_seconds=100)
    saved, clock = load_tournament_session(path, BLACK, max_total_seconds=100)
    assert len(saved.history) == 2
    assert 0 < clock.time_left() <= 100
    initial_time_left = clock.time_left()

    def stop_now(prompt):
        raise StopIteration()
    monkeypatch.setattr('builtins.input', stop_now)
    with pytest.raises(StopIteration):
        tournament_mode.run(BLACK, think_seconds=100, resume=True)
    saved2, clock2 = load_tournament_session(path, BLACK, max_total_seconds=100)
    assert _clock_state_snapshot(saved2) == _clock_state_snapshot(saved)
    assert clock2.time_left() == pytest.approx(initial_time_left, abs=0.005)

def test_time_budget_in_real_search_is_respected_for_short_game():
    state = GameState()
    player = AIPlayer(WHITE, total_seconds=0.1)
    begin = time.monotonic()
    chosen = player.choose_move(state)
    assert chosen and len(chosen) == 1
    assert time.monotonic() - begin < 1.0
    assert player.clock.time_left() >= 0.0

# --- GUI human input and tournament interactions ---

def wait_until(predicate, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("background worker did not finish within timeout")

def _mock_first_legal_move(self, state, estimated_moves_left=None):
    return [state.board.empty_cells()[0]]

def test_worker_does_not_mutate_live_state(monkeypatch):
    def choose(self, snapshot, estimated_moves_left=None):
        snapshot.apply_turn([snapshot.board.empty_cells()[0]])
        return [snapshot.board.empty_cells()[1]]
    monkeypatch.setattr(AIPlayer, "choose_move", choose)
    state = GameState()
    original_cells = state.board.cells.copy()
    player = AIPlayer(WHITE)
    worker = AIWorker()
    assert worker.start(player, state)
    assert not worker.start(player, state)
    wait_until(lambda: worker._finished.is_set())
    result = worker.poll()
    assert result.error is None and result.move is not None
    assert state.board.cells == original_cells
    assert not worker.busy and worker.poll() is None

def test_worker_discard_ignores_stale_move(monkeypatch):
    gate = Event()
    started = Event()
    def choose(self, snapshot, estimated_moves_left=None):
        started.set()
        gate.wait(1.5)
        return [snapshot.board.empty_cells()[0]]
    monkeypatch.setattr(AIPlayer, "choose_move", choose)
    worker = AIWorker()
    worker.start(AIPlayer(WHITE), GameState())
    wait_until(started.is_set)
    worker.discard()
    gate.set()
    wait_until(lambda: worker._finished.is_set())
    assert worker.poll().discarded

def test_human_white_confirm_and_undo_reverts_human_turn():
    controller = HumanGameController(WHITE)
    assert controller.can_input()
    controller.confirm_turn([(4, 5)])
    assert controller.state.to_move == BLACK
    assert not controller.can_input()
    controller.undo()
    assert len(controller.state.history) == 0
    assert controller.state.to_move == WHITE
    assert controller.can_input()

def test_human_black_does_not_undo_ais_opening(monkeypatch):
    monkeypatch.setattr(AIPlayer, "choose_move", _mock_first_legal_move)
    controller = HumanGameController(BLACK)
    assert not controller.can_input()
    controller.update()
    wait_until(lambda: controller.worker._finished.is_set())
    controller.update()
    assert controller.state.to_move == BLACK
    controller.undo()
    assert len(controller.state.history) == 1
    controller.confirm_turn([(4, 5)])
    assert controller.state.to_move == WHITE
    controller.undo()
    assert len(controller.state.history) == 1
    assert controller.state.to_move == BLACK

def test_human_undo_cancels_pending_ai_move(monkeypatch):
    gate = Event()
    def block_choose(self, snapshot, estimated_moves_left=None):
        gate.wait(1.0)
        return [snapshot.board.empty_cells()[0]]
    monkeypatch.setattr(AIPlayer, "choose_move", block_choose)
    controller = HumanGameController(WHITE)
    controller.confirm_turn([(4, 5)])
    controller.update()
    assert controller.worker.busy
    controller.undo()
    gate.set()
    wait_until(lambda: controller.worker._finished.is_set())
    controller.update()
    assert len(controller.state.history) == 0
    assert controller.state.to_move == WHITE

def test_human_restart_discards_old_result(monkeypatch):
    gate = Event()
    def block_choose(self, snapshot, estimated_moves_left=None):
        gate.wait(1.0)
        return [snapshot.board.empty_cells()[0]]
    monkeypatch.setattr(AIPlayer, "choose_move", block_choose)
    controller = HumanGameController(BLACK)
    controller.update()
    assert controller.worker.busy
    controller.reset()
    gate.set()
    wait_until(lambda: controller.worker._finished.is_set())
    controller.update()
    assert len(controller.state.history) == 0
    # The previous update may already have started a fresh AI opening.
    wait_until(lambda: controller.worker._finished is not None and controller.worker._finished.is_set())
    controller.update()
    assert len(controller.state.history) == 1

def test_visual_controller_pause_resume_undo_and_restart(monkeypatch):
    monkeypatch.setattr(AIPlayer, "choose_move", _mock_first_legal_move)
    controller = VisualSelfPlayController(delay_ms=0)
    controller.update()
    wait_until(lambda: controller.worker._finished.is_set())
    controller.toggle_pause()
    controller.update()
    assert len(controller.state.history) == 0
    controller.toggle_pause()
    controller.update()
    assert len(controller.state.history) == 1
    controller.undo()
    assert len(controller.state.history) == 0
    assert controller.paused
    controller.reset()
    assert not controller.paused and len(controller.state.history) == 0

def test_tournament_undo_exchange_both_colours():
    state = GameState()
    assert not undo_last_exchange(state, BLACK)
    state.apply_turn([(4, 5)])
    state.apply_turn([(0, 1)])
    assert undo_last_exchange(state, BLACK)
    assert len(state.history) == 0 and state.to_move == WHITE

    state = GameState()
    state.apply_turn([(4, 5)])
    assert not undo_last_exchange(state, WHITE)
    state.apply_turn([(0, 1)])
    state.apply_turn([(1, 1)])
    assert undo_last_exchange(state, WHITE)
    assert len(state.history) == 1 and state.to_move == BLACK

def test_cli_dispatch_gui_selfplay(monkeypatch):
    import main
    calls = []
    monkeypatch.setattr(main.self_play, "run", lambda **kw: calls.append(kw))
    monkeypatch.setattr(sys, "argv", ["main.py", "selfplay", "--gui", "--delay-ms", "75"])
    main.main()
    assert calls == [{"think_seconds": 600.0, "delay_ms": 75}]

def test_pygame_smoke_if_installed(monkeypatch):
    pygame = pytest.importorskip("pygame")
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    from src.gui.app import GuiApp
    controller = HumanGameController(WHITE)
    app = GuiApp(controller.state, controller.confirm_turn, controller.undo,
                 state_provider=lambda: controller.state,
                 input_enabled=controller.can_input, status_provider=controller.status)
    try:
        assert app.run_once()
        assert app.state.to_move == WHITE
        # UI must ignore invalid board clicks without mutating game.
        app._handle_cell_click((-100, -100))
        assert len(controller.state.history) == 0
    finally:
        app.quit()

# Full games, benchmarks and colour-swapped matches

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