"""Coordinate helpers for the 61-cell Catchup hexagon (five cells per side).

The labels match Figure 2 of the official Catchup rules.
"""

from typing import Iterator, Tuple

N = 5
NUM_ROWS = 2 * N - 1
NUM_COLS = 2 * N - 1
COL_LETTERS = "ABCDEFGHI"[:NUM_COLS]

Cell = Tuple[int, int]  # (column, row); column is 0-indexed, row is 1-indexed.

NEIGHBOUR_DELTAS = ((1, 1), (1, 0), (0, -1), (-1, -1), (-1, 0), (0, 1))


def col_bounds(row: int) -> Tuple[int, int]:
    if not (1 <= row <= NUM_ROWS):
        raise ValueError(f"row {row} out of range 1..{NUM_ROWS}")
    if row <= N:
        return 0, row + N - 2
    return row - N, NUM_COLS - 1


def is_valid(cell: Cell) -> bool:
    col, row = cell
    if not (1 <= row <= NUM_ROWS):
        return False
    lo, hi = col_bounds(row)
    return lo <= col <= hi


def all_cells() -> Iterator[Cell]:
    for row in range(1, NUM_ROWS + 1):
        lo, hi = col_bounds(row)
        for col in range(lo, hi + 1):
            yield col, row


# Cell geometry is immutable, so adjacent cells are precomputed exactly once.
# Return an iterator rather than the cached tuple to keep existing callers' API.
_NEIGHBOUR_MAP = {
    cell: tuple(
        adjacent for dc, dr in NEIGHBOUR_DELTAS
        if is_valid(adjacent := (cell[0] + dc, cell[1] + dr))
    )
    for cell in all_cells()
}


def neighbours(cell: Cell) -> Iterator[Cell]:
    if not is_valid(cell):
        raise ValueError(f"invalid Catchup cell: {cell!r}")
    return iter(_NEIGHBOUR_MAP[cell])


def to_notation(cell: Cell) -> str:
    if not is_valid(cell):
        raise ValueError(f"invalid Catchup cell: {cell!r}")
    col, row = cell
    return f"{COL_LETTERS[col]}{row}"


def from_notation(text: str) -> Cell:
    text = text.strip().upper()
    if len(text) != 2 or text[0] not in COL_LETTERS or text[1] not in "123456789":
        raise ValueError(f"'{text}' is not a valid Catchup cell label")
    cell = COL_LETTERS.index(text[0]), int(text[1])
    if not is_valid(cell):
        raise ValueError(f"'{text}' is not a valid cell on this board")
    return cell