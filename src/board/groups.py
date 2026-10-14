"""
Connected-group sizes (flood fill).

SCAFFOLDING NOTE: this recomputes groups from scratch with a BFS every call,
which is fine for a placeholder but far too slow to call at every search node.
A real engine typically tracks group sizes incrementally (e.g. union-find
updated on each placement) - that is left for you to design and implement.
"""

from collections import deque
from typing import List

from .board import Board
from .coordinates import Cell


def group_containing(board: Board, cell: Cell) -> List[Cell]:
    colour = board.cells[cell]
    if colour is None:
        return []
    seen = {cell}
    queue = deque([cell])
    while queue:
        current = queue.popleft()
        for n in board.neighbours_of_colour(current, colour):
            if n not in seen:
                seen.add(n)
                queue.append(n)
    return list(seen)


def group_sizes(board: Board, colour: str) -> List[int]:
    """All group sizes for `colour`, largest first."""
    visited = set()
    sizes = []
    for cell in board.stones_of(colour):
        if cell in visited:
            continue
        group = group_containing(board, cell)
        visited.update(group)
        sizes.append(len(group))
    return sorted(sizes, reverse=True)


def largest_group_size(board: Board, colour: str) -> int:
    sizes = group_sizes(board, colour)
    return sizes[0] if sizes else 0
