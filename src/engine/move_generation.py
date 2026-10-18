"""Whole-turn move generation for Catchup.

`legal_turns` is exhaustive and follows the rules exactly: a turn is an
unordered combination of 1, 2 or 3 DIFFERENT empty cells, except White's
opening, which must contain one cell. `ranked_candidate_turns` is an explicitly
SELECTIVE approximation used for tractable midgame search; it never claims
that the reduced tree is the complete minimax tree.
"""
from itertools import combinations
from typing import Dict, Iterator, List, Optional, Tuple
import heapq
import time

from ..board.board import BLACK, WHITE, other
from ..board.coordinates import Cell, neighbours
from ..game.state import GameState, Turn


class SearchTimeout(Exception):
    """Internal cancellation signal; any applied turn must be undone in finally."""


def check_deadline(deadline: Optional[float]) -> None:
    if deadline is not None and time.monotonic() >= deadline:
        raise SearchTimeout()


def legal_turns(state: GameState) -> Iterator[Turn]:
    """Enumerate every legal turn once, without mutating `state`."""
    if state.is_game_over():
        return
    empties = state.board.empty_cells()
    for length in range(1, min(state.stones_allowed_this_turn(), len(empties)) + 1):
        for choice in combinations(empties, length):
            yield list(choice)


def _component_map(state: GameState, colour: str) -> Tuple[Dict[Cell, int], List[int]]:
    """Map stones to connected-component indices and component sizes."""
    board = state.board
    component: Dict[Cell, int] = {}
    sizes: List[int] = []
    for stone in board.stones_of(colour):
        if stone in component:
            continue
        index = len(sizes)
        stack = [stone]
        component[stone] = index
        size = 0
        while stack:
            cell = stack.pop()
            size += 1
            for adjacent in neighbours(cell):
                if board.cells[adjacent] == colour and adjacent not in component:
                    component[adjacent] = index
                    stack.append(adjacent)
        sizes.append(size)
    return component, sizes


def _cell_scores(state: GameState) -> Dict[Cell, float]:
    """Cheap local ranking; this is a move-ordering heuristic, NOT game evaluation."""
    board = state.board
    mover = state.to_move
    mine_map, mine_sizes = _component_map(state, mover)
    foe_map, foe_sizes = _component_map(state, other(mover))
    scores: Dict[Cell, float] = {}
    for cell in board.empty_cells():
        q, r = cell[0] - 4, 5 - cell[1]
        distance = max(abs(q), abs(r), abs(q + r))
        adjacent = tuple(neighbours(cell))
        mine = {mine_map[n] for n in adjacent if n in mine_map}
        foes = {foe_map[n] for n in adjacent if n in foe_map}
        # Good opening cells are central; later favour existing groups,
        # bridging several groups, and contesting the opponent's frontier.
        score = 0.45 * (4 - distance)
        score += 2.5 * sum(min(mine_sizes[i], 7) ** 0.5 for i in mine)
        score += 2.1 * sum(min(foe_sizes[i], 7) ** 0.5 for i in foes)
        score += 5.0 * max(0, len(mine) - 1)
        score += 1.5 * max(0, len(foes) - 1)
        scores[cell] = score
    return scores


def ranked_candidate_turns(
    state: GameState,
    max_branch: int = 10,
    max_cells: int = 12,
    full_width: bool = False,
    deadline: Optional[float] = None,
) -> List[Turn]:
    """Rank legal complete turns with bounded memory in selective mode.

    Full-width mode still enumerates and orders every legal turn. In normal
    mode, keep only the highest-ranked `max_branch` combinations in a heap,
    plus the best action of each permitted length for tactical diversity.
    This is still a SELECTIVE search (not guaranteed globally optimal).
    """
    check_deadline(deadline)
    if state.is_game_over():
        return []
    if max_branch < 1 or max_cells < 1:
        raise ValueError("max_branch and max_cells must be positive")

    scores = _cell_scores(state)
    cell_pool = (
        state.board.empty_cells() if full_width
        else heapq.nlargest(max_cells, scores, key=scores.__getitem__)
    )
    board_order = {cell: i for i, cell in enumerate(state.board.cells)}
    cell_pool.sort(key=board_order.__getitem__)
    max_length = min(state.stones_allowed_this_turn(), len(cell_pool))
    if max_length == 0:
        return []

    # This is substantially cheaper than recomputing neighbour sets for
    # every candidate inside the combinatorial loop.
    adjacent = {cell: set(neighbours(cell)) for cell in cell_pool}
    heap = []
    all_choices = [] if full_width else None
    best_by_length = {}
    serial = 0
    for length in range(1, max_length + 1):
        for cells in combinations(cell_pool, length):
            serial += 1
            if serial % 128 == 0:
                check_deadline(deadline)
            quick = sum(scores[cell] for cell in cells)
            for i in range(len(cells)):
                quick += 2.0 * sum(c in adjacent[cells[i]] for c in cells[i + 1:])
            # -serial makes earlier board-ordered combinations win exact ties.
            item = (quick, -serial, cells)
            if full_width:
                all_choices.append(item)
            else:
                if length not in best_by_length or item > best_by_length[length]:
                    best_by_length[length] = item
                if len(heap) < max_branch:
                    heapq.heappush(heap, item)
                elif item > heap[0]:
                    heapq.heapreplace(heap, item)

    if full_width:
        # All actions included, sorted: exact search is possible.
        all_choices.sort(reverse=True)
        return [list(item[2]) for item in all_choices]

    selected = []
    selected_turns = set()
    for length in range(1, max_length + 1):
        if len(selected) == max_branch:
            break
        item = best_by_length[length]
        selected.append(item)
        selected_turns.add(item[2])
    for item in sorted(heap, reverse=True):
        if len(selected) == max_branch:
            break
        if item[2] not in selected_turns:
            selected.append(item)
            selected_turns.add(item[2])
    selected.sort(reverse=True)
    check_deadline(deadline)
    return [list(item[2]) for item in selected]