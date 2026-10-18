"""Rule, state, undo and persistence regression tests for Catchup Phase 1."""

import json
import random

import pytest

from src.board.board import BLACK, WHITE, Board
from src.board.coordinates import (
    all_cells, col_bounds, from_notation, is_valid, neighbours, to_notation
)
from src.board.groups import group_sizes, largest_group_size
from src.game.notation import format_turn, parse_turn
from src.game.rules import compare_group_lists, max_stones_allowed
from src.game.state import GameState
from src.persistence.save_load import _state_to_dict, load_game, save_game


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


def test_invalid_cells_are_rejected_by_board():
    board = Board()
    with pytest.raises(ValueError):
        board.place((8, 1), WHITE)
    with pytest.raises(ValueError):
        board.place(from_notation("E5"), "X")
    with pytest.raises(ValueError):
        board.remove(from_notation("E5"))
    board.place(from_notation("E5"), WHITE)
    with pytest.raises(ValueError):
        board.place(from_notation("E5"), BLACK)
    with pytest.raises(ValueError):
        board.is_empty((8, 1))


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