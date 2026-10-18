"""Validated 61-cell Catchup board supporting copy, place and undo."""

from typing import Dict, List, Optional

from . import coordinates as coords
from .coordinates import Cell

EMPTY: Optional[str] = None
WHITE = "W"
BLACK = "B"


def other(colour: str) -> str:
    if colour not in (WHITE, BLACK):
        raise ValueError(f"invalid stone colour: {colour!r}")
    return BLACK if colour == WHITE else WHITE


class Board:
    def __init__(self) -> None:
        self.cells: Dict[Cell, Optional[str]] = {c: EMPTY for c in coords.all_cells()}

    def copy(self) -> "Board":
        result = Board()
        result.cells = dict(self.cells)
        return result

    def place(self, cell: Cell, colour: str) -> None:
        if not isinstance(cell, tuple) or len(cell) != 2:
            raise ValueError(f"invalid Catchup cell: {cell!r}")
        if cell not in self.cells:
            raise ValueError(f"invalid Catchup cell: {cell!r}")
        if colour not in (WHITE, BLACK):
            raise ValueError(f"invalid stone colour: {colour!r}")
        if self.cells[cell] is not EMPTY:
            raise ValueError(f"cell {coords.to_notation(cell)} is already occupied")
        self.cells[cell] = colour

    def remove(self, cell: Cell) -> None:
        if not isinstance(cell, tuple) or len(cell) != 2:
            raise ValueError(f"invalid Catchup cell: {cell!r}")
        if cell not in self.cells:
            raise ValueError(f"invalid Catchup cell: {cell!r}")
        if self.cells[cell] is EMPTY:
            raise ValueError(f"cell {coords.to_notation(cell)} is already empty")
        self.cells[cell] = EMPTY

    def is_empty(self, cell: Cell) -> bool:
        if not isinstance(cell, tuple) or len(cell) != 2:
            raise ValueError(f"invalid Catchup cell: {cell!r}")
        if cell not in self.cells:
            raise ValueError(f"invalid Catchup cell: {cell!r}")
        return self.cells[cell] is EMPTY

    def empty_cells(self) -> List[Cell]:
        return [c for c, value in self.cells.items() if value is EMPTY]

    def is_full(self) -> bool:
        return all(value is not EMPTY for value in self.cells.values())

    def stones_of(self, colour: str) -> List[Cell]:
        if colour not in (WHITE, BLACK):
            raise ValueError(f"invalid stone colour: {colour!r}")
        return [c for c, value in self.cells.items() if value == colour]

    def neighbours_of_colour(self, cell: Cell, colour: str) -> List[Cell]:
        if colour not in (WHITE, BLACK):
            raise ValueError(f"invalid stone colour: {colour!r}")
        return [n for n in coords.neighbours(cell) if self.cells[n] == colour]