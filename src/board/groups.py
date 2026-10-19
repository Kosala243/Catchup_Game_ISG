"""
- Connected groups of same-colour stones on the 61-cell Catchup board.
- Each group traversal visits its occupied cells once. This avoids invoking a
- separate full group search for each stone when computing all group sizes.
"""
from collections import deque
from typing import List

from .board import Board
from .coordinates import Cell, neighbours

def group_containing(board: Board, cell: Cell) -> List[Cell]:
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
    sizes = group_sizes(board, colour)
    return sizes[0] if sizes else 0