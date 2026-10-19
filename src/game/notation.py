"""
Turn <-> text notation, for communicating moves at the tournament table.
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