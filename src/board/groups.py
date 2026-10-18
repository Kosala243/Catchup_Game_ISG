"""Connected groups of same-colour stones on the 61-cell Catchup board.

Each group traversal visits its occupied cells once. This avoids invoking a
separate full group search for each stone when computing all group sizes.
"""
from collections import deque
from typing import List

from .board import Board
from .coordinates import Cell, neighbours


def group_containing(board: Board, cell: Cell) -> List[Cell]:
    """Return all stones connected to ``cell`` (or [] for an empty cell).

    This preserves the established API: passing an invalid cell raises
    KeyError; valid empty cells yield an empty group.
    """
    colour = board.cells[cell]
    if colour is None:
        return []

    group = {cell}
    pending = deque((cell,))
    while pending:
        for adjacent in neighbours(pending.popleft()):
            if adjacent not in group and board.cells[adjacent] == colour:
                group.add(adjacent)
                pending.append(adjacent)
    return list(group)


def group_sizes(board: Board, colour: str) -> List[int]:
    """Compute every connected-component size once, largest first."""
    # stones_of validates the colour, preserving Board's error behaviour.
    stones = board.stones_of(colour)
    remaining = set(stones)
    sizes: List[int] = []

    while remaining:
        root = remaining.pop()
        pending = [root]
        size = 0
        while pending:
            cell = pending.pop()
            size += 1
            for adjacent in neighbours(cell):
                if adjacent in remaining:
                    remaining.remove(adjacent)
                    pending.append(adjacent)
        sizes.append(size)
    sizes.sort(reverse=True)
    return sizes


def largest_group_size(board: Board, colour: str) -> int:
    """The size of the largest group; zero when ``colour`` has no stones."""
    sizes = group_sizes(board, colour)
    return sizes[0] if sizes else 0
