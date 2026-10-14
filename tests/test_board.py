from src.board import coordinates as coords
from src.board.board import Board, WHITE


def test_total_cell_count():
    assert len(list(coords.all_cells())) == 61


def test_notation_round_trip():
    for cell in coords.all_cells():
        assert coords.from_notation(coords.to_notation(cell)) == cell


def test_corner_has_three_neighbours():
    # A5 is a corner of the hexagon (left-most point of the widest row).
    assert len(list(coords.neighbours((0, 5)))) == 3


def test_centre_has_six_neighbours():
    # E5 is the centre cell.
    assert len(list(coords.neighbours((4, 5)))) == 6


def test_place_and_remove():
    board = Board()
    cell = (4, 5)
    board.place(cell, WHITE)
    assert not board.is_empty(cell)
    board.remove(cell)
    assert board.is_empty(cell)
