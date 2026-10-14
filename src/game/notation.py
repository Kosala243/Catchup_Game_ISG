"""
Turn <-> text notation, for communicating moves at the tournament table.

ASSUMPTION TO VERIFY: the rules PDF only fixes single-cell labels (e.g. "D5"),
not how to write a multi-stone turn. This module joins cells with spaces, e.g.
a two-stone turn as "D5 E6". Confirm this against whatever the tournament
organisers expect before relying on it, and adjust if needed.
"""

from typing import List

from ..board.coordinates import Cell, from_notation, to_notation


def format_turn(cells: List[Cell]) -> str:
    return " ".join(to_notation(c) for c in cells)


def parse_turn(text: str) -> List[Cell]:
    tokens = text.strip().split()
    if not tokens:
        raise ValueError("empty move")
    return [from_notation(t) for t in tokens]
