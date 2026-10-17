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
    """Return ordered legal actions.

    With `full_width=True`, every action is included (for exact searches).
    Otherwise search is selective: choose a local cell pool, rank complete
    turns, and retain one action of each legal length if the branch cap allows.
    A reduced action set is NOT guaranteed to contain the minimax best move.
    """
    check_deadline(deadline)
    if state.is_game_over():
        return []
    if max_branch < 1 or max_cells < 1:
        raise ValueError("max_branch and max_cells must be positive")
    scores = _cell_scores(state)
    if full_width:
        cell_pool = state.board.empty_cells()
    else:
        cell_pool = heapq.nlargest(max_cells, scores, key=scores.__getitem__)
        # Combine priority cells with a few opponent-adjacent defensive cells.
        # This pool remains bounded to control 3-stone combinatorics.
    board_order = {cell: i for i, cell in enumerate(state.board.cells)}
    cell_pool.sort(key=board_order.__getitem__)  # same canonical order as exhaustive generator
    max_length = min(state.stones_allowed_this_turn(), len(cell_pool))
    if max_length == 0:
        return []

    candidates = []
    iter_count = 0
    for length in range(1, max_length + 1):
        for cells in combinations(cell_pool, length):
            iter_count += 1
            if iter_count % 128 == 0:
                check_deadline(deadline)
            quick = sum(scores[c] for c in cells)
            # A useful tie-break: a multi-stone turn with adjacent placements
            # can create a contiguous bridge rather than isolated stones.
            for i in range(len(cells)):
                adjoining = set(neighbours(cells[i]))
                quick += 2.0 * sum(c in adjoining for c in cells[i + 1:])
            # Stable, deterministic ranking on equal scores.
            candidates.append((quick, cells))
    candidates.sort(key=lambda item: (-item[0], item[1]))
    if full_width:
        return [list(cells) for _, cells in candidates]

    selected: List[Tuple[Cell, ...]] = []
    seen = set()
    # Preserve action-size diversity when the branch cap allows it: placing
    # fewer stones may avoid gifting an opponent a three-stone bonus.
    for length in range(1, max_length + 1):
        if len(selected) >= max_branch:
            break
        for _, cells in candidates:
            if len(cells) == length:
                if cells not in seen:
                    selected.append(cells)
                    seen.add(cells)
                break
    for _, cells in candidates:
        if len(selected) >= max_branch:
            break
        if cells not in seen:
            selected.append(cells)
            seen.add(cells)
    # Sort final actions by their original quick score, not by selection stage.
    quick_by_turn = {cells: quick for quick, cells in candidates}
    selected.sort(key=lambda c: (-quick_by_turn[c], c))
    check_deadline(deadline)
    return [list(cells) for cells in selected]