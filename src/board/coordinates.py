"""
Hex-grid coordinate system for the Catchup board (Figure 2 of the assignment PDF).

SCAFFOLDING NOTE: this module was drafted with AI assistance to get the project
running end-to-end. Geometry/coordinate handling is a mechanical concern, but the
assignment still treats "state-action representation" as something you must own -
review this file, adapt it to however you actually want to represent state, and
disclose it in AI_USAGE.md if you keep any of it as-is.

Board layout: a hexagon with N=5 cells per side, 61 cells total, labelled with
columns 'A'..'I' and rows 1..9 exactly as shown in Figure 2 of the rules PDF.
"""

from typing import Iterator, Tuple

N = 5                      # cells per side
NUM_ROWS = 2 * N - 1       # 9
NUM_COLS = 2 * N - 1       # 9
COL_LETTERS = "ABCDEFGHI"[:NUM_COLS]

Cell = Tuple[int, int]     # (col, row), 0-indexed col, 1-indexed row

# Six neighbour offsets (delta_col, delta_row) for this particular layout,
# derived from the row-dependent column bounds below. See docs/design_notes.md.
NEIGHBOUR_DELTAS = ((1, 1), (1, 0), (0, -1), (-1, -1), (-1, 0), (0, 1))


def col_bounds(row: int) -> Tuple[int, int]:
    """Inclusive (min_col, max_col) of valid columns for a given 1-indexed row."""
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
    """Yield all 61 valid (col, row) cells on the board."""
    for row in range(1, NUM_ROWS + 1):
        lo, hi = col_bounds(row)
        for col in range(lo, hi + 1):
            yield (col, row)


def neighbours(cell: Cell) -> Iterator[Cell]:
    col, row = cell
    for dc, dr in NEIGHBOUR_DELTAS:
        n = (col + dc, row + dr)
        if is_valid(n):
            yield n


def to_notation(cell: Cell) -> str:
    col, row = cell
    return f"{COL_LETTERS[col]}{row}"


def from_notation(text: str) -> Cell:
    text = text.strip().upper()
    col = COL_LETTERS.index(text[0])
    row = int(text[1:])
    cell = (col, row)
    if not is_valid(cell):
        raise ValueError(f"'{text}' is not a valid cell on this board")
    return cell
