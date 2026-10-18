"""Regression tests for independently checkable Catchup rules and interfaces."""
import math
import random

import pytest

from src.board.board import BLACK, WHITE, Board
from src.board.coordinates import all_cells, is_valid, neighbours, to_notation, from_notation
from src.board.groups import group_containing, group_sizes, largest_group_size
from src.engine.evaluation import describe_evaluation, evaluate
from src.engine.move_generation import ranked_candidate_turns
from src.engine.search import iterative_deepening
from src.game.rules import compare_group_lists, max_stones_allowed
from src.game.state import GameState


def reference_groups(board, colour):
    """Reference traversal uses only the neighbour geometry, not group code."""
    available = {c for c, value in board.cells.items() if value == colour}
    sizes = []
    while available:
        queue = [available.pop()]
        count = 0
        while queue:
            node = queue.pop()
            count += 1
            for n in neighbours(node):
                if n in available:
                    available.remove(n)
                    queue.append(n)
        sizes.append(count)
    return sorted(sizes, reverse=True)


def snapshot(state):
    return (
        tuple(state.board.cells.items()), dict(state.scores), state.to_move,
        state.is_opening_move, state.score_increased_last_turn, len(state.history),
    )


def test_rules_opening_bonus_and_group_tie_breaking():
    state = GameState()
    assert state.stones_allowed_this_turn() == 1
    state.apply_turn([(4, 5)])
    assert state.to_move == BLACK
    assert not state.score_increased_last_turn
    assert state.stones_allowed_this_turn() == 2
    assert max_stones_allowed(5, 5, True) == 3
    assert max_stones_allowed(5, 4, True) == 2
    assert max_stones_allowed(5, 7, False) == 2
    assert compare_group_lists([6, 5, 5, 3], [6, 5, 4, 3]) == 1
    assert compare_group_lists([6, 5, 4, 3], [6, 5, 5, 3]) == -1
    assert compare_group_lists([4, 3], [4, 3]) == 0
    assert compare_group_lists([3], [3, 1]) == -1
    assert compare_group_lists([3, 1], [3]) == 1
    assert compare_group_lists([], []) == 0


def test_61_cell_geometry_and_symmetric_cached_neighbors():
    cells = list(all_cells())
    assert len(cells) == len(set(cells)) == 61
    for cell in cells:
        assert from_notation(to_notation(cell)) == cell
        adj = list(neighbours(cell))
        assert adj == list(neighbours(cell))
        assert len(adj) == len(set(adj))
        assert all(is_valid(n) and cell in neighbours(n) for n in adj)


@pytest.mark.parametrize('seed', [0, 2, 11, 26, 103, 4096, 9923])
def test_full_game_group_calculation_and_undo_matches_reference(seed):
    rng = random.Random(seed)
    state = GameState()
    states = [snapshot(state)]
    while not state.is_game_over():
        blanks = state.board.empty_cells()
        action_len = rng.randint(1, min(state.stones_allowed_this_turn(), len(blanks)))
        state.apply_turn(rng.sample(blanks, action_len))
        for colour in (WHITE, BLACK):
            sizes = reference_groups(state.board, colour)
            assert group_sizes(state.board, colour) == sizes
            assert largest_group_size(state.board, colour) == (sizes[0] if sizes else 0)
            for c in state.board.stones_of(colour):
                assert len(group_containing(state.board, c)) in sizes
        assert len(state.history) <= 61
        states.append(snapshot(state))
    assert sum(v is not None for v in state.board.cells.values()) == 61
    state.winner()
    for target in states[-2::-1]:
        state.undo()
        assert snapshot(state) == target


def test_invalid_actions_are_rejected_atomically():
    s = GameState()
    before = snapshot(s)
    for move in (None, [], [[4, 5]], [(4, 5), (4, 5)], [(20, 20)], [None]):
        with pytest.raises(ValueError):
            s.apply_turn(move)
        assert snapshot(s) == before
    board = Board()
    for malformed in ([4, 5], None, (4,), (100, 100)):
        with pytest.raises(ValueError):
            board.place(malformed, WHITE)


def test_low_branch_cap_does_not_force_single_stone_turn(monkeypatch):
    import src.engine.move_generation as generation
    s = GameState()
    s.apply_turn([(4, 5)])
    assert s.stones_allowed_this_turn() == 2
    # Uniform positive scores make every best-ranked two-stone action
    # outrank every one-stone action for the same candidate pool.
    monkeypatch.setattr(generation, '_cell_scores', lambda state: {
        cell: 10.0 for cell in state.board.empty_cells()
    })
    action = ranked_candidate_turns(s, max_branch=1, max_cells=5)
    assert len(action) == 1 and len(action[0]) == 2
    trial = s.copy()
    trial.apply_turn(action[0])
    assert len(trial.history) == 2


def test_full_width_still_enumerates_all_turn_sizes():
    from experiments.phase6_common import build_position
    from src.engine.move_generation import legal_turns
    s = build_position(42, 3)
    before = snapshot(s)
    expected = {tuple(a) for a in legal_turns(s)}
    actual = {tuple(a) for a in ranked_candidate_turns(s, full_width=True)}
    assert actual == expected
    assert snapshot(s) == before


def test_evaluation_breakdown_is_exactly_the_engines_score():
    from experiments.phase6_common import build_position
    s = build_position(44, 19)
    for colour in (WHITE, BLACK):
        info = describe_evaluation(s, colour)
        assert info['score'] == pytest.approx(evaluate(s, colour))
        assert not info['terminal']
        assert isinstance(info['own_features'], float)
    while not s.is_game_over():
        s.apply_turn([s.board.empty_cells()[0]])
    for colour in (WHITE, BLACK):
        info = describe_evaluation(s, colour)
        assert info['terminal']
        assert info['score'] == evaluate(s, colour)


@pytest.mark.parametrize('value', [float('nan'), float('inf'), float('-inf'), '10', None, True])
def test_search_rejects_nonfinite_or_invalid_budget(value):
    with pytest.raises(ValueError, match='time_budget_seconds'):
        iterative_deepening(GameState(), value, WHITE)
