"""
Board state: which stones sit where.

SCAFFOLDING NOTE: placeholder state representation (a plain dict) so the rest
of the project runs end-to-end. This is exactly the kind of "state-action
representation" the assignment expects you to design yourself - replace it
with whatever representation suits your search (e.g. flat arrays/bitboards for
speed) and disclose in AI_USAGE.md if any of this scaffold survives into your
submission.
"""

from typing import Dict, List, Optional

from . import coordinates as coords
from .coordinates import Cell

EMPTY: Optional[str] = None
WHITE = "W"
BLACK = "B"


def other(colour: str) -> str:
    return BLACK if colour == WHITE else WHITE


class Board:
    def __init__(self) -> None:
        self.cells: Dict[Cell, Optional[str]] = {c: EMPTY for c in coords.all_cells()}

    def copy(self) -> "Board":
        b = Board()
        b.cells = dict(self.cells)
        return b

    def place(self, cell: Cell, colour: str) -> None:
        if self.cells[cell] is not EMPTY:
            raise ValueError(f"cell {coords.to_notation(cell)} is already occupied")
        self.cells[cell] = colour

    def remove(self, cell: Cell) -> None:
        """Used by undo: clears a cell back to empty."""
        self.cells[cell] = EMPTY

    def is_empty(self, cell: Cell) -> bool:
        return self.cells[cell] is EMPTY

    def empty_cells(self) -> List[Cell]:
        return [c for c, v in self.cells.items() if v is EMPTY]

    def is_full(self) -> bool:
        return all(v is not EMPTY for v in self.cells.values())

    def stones_of(self, colour: str) -> List[Cell]:
        return [c for c, v in self.cells.items() if v == colour]

    def neighbours_of_colour(self, cell: Cell, colour: str) -> List[Cell]:
        return [n for n in coords.neighbours(cell) if self.cells[n] == colour]
