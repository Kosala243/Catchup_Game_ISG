"""Phase 4: whole-game time accounting, restart safety, tournament integration."""
import json
import math
import time

import pytest

from src.board.board import WHITE, BLACK
from src.engine.player import AIPlayer
from src.engine.time_manager import Clock, allocate_time
from src.engine import search
from src.game.state import GameState
from src.persistence.save_load import (
    load_game, save_game, save_tournament_session, load_tournament_session,
)
from src.modes import tournament_mode


class FakeTime:
    def __init__(self, value=1000.0):
        self.value = value

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


def state_snapshot(s):
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


def test_player_allocates_more_as_board_fills():
    state = GameState()
    player = AIPlayer(WHITE, 600)
    first_budget = player.move_budget(state)
    state.apply_turn([(4, 5)])
    state.apply_turn([(0, 1), (0, 2)])
    assert state.to_move == WHITE
    next_budget = player.move_budget(state)
    assert next_budget > first_budget


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


def test_player_checks_colour_before_search():
    state = GameState()
    with pytest.raises(ValueError):
        AIPlayer(BLACK).choose_move(state)


def test_player_refuses_search_with_expired_clock():
    state = GameState()
    player = AIPlayer(WHITE, total_seconds=60, remaining_seconds=0)
    with pytest.raises(TimeoutError):
        player.choose_move(state)


def test_tournament_session_restores_board_history_and_remaining_time(tmp_path):
    state = GameState()
    state.apply_turn([(4, 5)])
    state.apply_turn([(0, 1), (1, 1)])
    before = state_snapshot(state)
    clock = Clock(total_seconds=600, remaining_seconds=153.25)
    path = tmp_path / 'session.json'
    save_tournament_session(state, str(path), WHITE, clock)
    restored, restored_clock = load_tournament_session(str(path), WHITE)
    assert state_snapshot(restored) == before
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
    assert state_snapshot(load_game(path)) == state_snapshot(state)
    with pytest.raises(ValueError, match='no tournament clock'):
        load_tournament_session(path, WHITE)


def test_load_game_can_open_tournament_session(tmp_path):
    state = GameState()
    state.apply_turn([(4, 5)])
    path = str(tmp_path / 'session.json')
    save_tournament_session(state, path, BLACK, Clock(600, remaining_seconds=50))
    assert state_snapshot(load_game(path)) == state_snapshot(state)


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


def test_reject_checkpoint_while_clock_running(tmp_path):
    clock = Clock(100)
    clock.start_move()
    with pytest.raises(RuntimeError):
        save_tournament_session(GameState(), str(tmp_path / 'session.json'), WHITE, clock)
    clock.stop_move()


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
    assert state_snapshot(saved2) == state_snapshot(saved)
    assert clock2.time_left() == pytest.approx(initial_time_left, abs=0.005)


def test_time_budget_in_real_search_is_respected_for_short_game():
    state = GameState()
    player = AIPlayer(WHITE, total_seconds=0.1)
    begin = time.monotonic()
    chosen = player.choose_move(state)
    assert chosen and len(chosen) == 1
    assert time.monotonic() - begin < 1.0
    assert player.clock.time_left() >= 0.0