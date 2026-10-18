"""Exhaustive legal turns and fast, tactical *selective* turn ranking.

A Catchup turn is one unordered combination of 1-3 empty cells. Selection
never changes legality. Candidate ranking uses prospective group connections,
not simply the sum of independent stone values. It is not a game-theoretic
proof that excluded turns are inferior.
"""
from itertools import combinations
import heapq
import time
from typing import Dict, Iterator, List, Optional, Tuple

from ..board.board import other
from ..board.coordinates import Cell, neighbours
from ..game.state import GameState, Turn


class SearchTimeout(Exception):
    """Stop an unfinished iteration; search must restore its state."""


def check_deadline(deadline: Optional[float]) -> None:
    if deadline is not None and time.monotonic() >= deadline:
        raise SearchTimeout()


def legal_turns(state: GameState) -> Iterator[Turn]:
    if state.is_game_over():
        return
    empties = state.board.empty_cells()
    for size in range(1, min(state.stones_allowed_this_turn(), len(empties)) + 1):
        for cells in combinations(empties, size):
            yield list(cells)


def _component_map(state: GameState, colour: str) -> Tuple[Dict[Cell, int], List[int]]:
    """Map occupied cells to component ids and component sizes."""
    board = state.board
    mapping: Dict[Cell, int] = {}
    sizes: List[int] = []
    for cell in board.stones_of(colour):
        if cell in mapping:
            continue
        number = len(sizes)
        stack = [cell]
        mapping[cell] = number
        size = 0
        while stack:
            current = stack.pop()
            size += 1
            for adjacent in neighbours(current):
                if board.cells[adjacent] == colour and adjacent not in mapping:
                    mapping[adjacent] = number
                    stack.append(adjacent)
        sizes.append(size)
    return mapping, sizes


def _cell_scores(state: GameState) -> Dict[Cell, float]:
    """Lightweight first-pass priority; later rank full turns tactically."""
    mine, mine_sizes = _component_map(state, state.to_move)
    foe, foe_sizes = _component_map(state, other(state.to_move))
    result: Dict[Cell, float] = {}
    for cell in state.board.empty_cells():
        q, r = cell[0] - 4, 5 - cell[1]
        centrality = 4 - max(abs(q), abs(r), abs(q + r))
        vicinity = tuple(neighbours(cell))
        own = {mine[n] for n in vicinity if n in mine}
        enemy = {foe[n] for n in vicinity if n in foe}
        result[cell] = (
            0.5 * centrality
            + 2.4 * sum(min(mine_sizes[i], 8) ** 0.5 for i in own)
            + 2.2 * sum(min(foe_sizes[i], 8) ** 0.5 for i in enemy)
            + 5.5 * max(0, len(own) - 1)
            + 4.0 * max(0, len(enemy) - 1)
        )
    return result


def _turn_tactical_score(
    state: GameState, cells: Tuple[Cell, ...], base: Dict[Cell, float],
    mine: Dict[Cell, int], mine_sizes: List[int],
    foe: Dict[Cell, int], foe_sizes: List[int],
    adjacent: Dict[Cell, set],
) -> float:
    """Estimate complete-turn synergy without making and undoing the turn.

    This computes groups that would be joined by up to three NEW stones,
    accounting for direct adjacency AND an existing component shared by
    multiple newly placed stones.
    """
    count = len(cells)
    links = [{mine[n] for n in adjacent[cell] if n in mine} for cell in cells]
    parent = list(range(count))

    def root(i: int) -> int:
        while parent[i] != i:
            i = parent[i]
        return i

    for i in range(count):
        for j in range(i + 1, count):
            if cells[j] in adjacent[cells[i]] or links[i].intersection(links[j]):
                parent[root(j)] = root(i)

    clusters: Dict[int, Tuple[int, set]] = {}
    for i in range(count):
        r = root(i)
        placed, existing = clusters.get(r, (0, set()))
        clusters[r] = placed + 1, existing | links[i]
    potential = max([state.scores[state.to_move]] + [
        placed + sum(mine_sizes[k] for k in existing)
        for placed, existing in clusters.values()
    ])
    growth = max(0, potential - state.scores[state.to_move])
    merge_count = sum(max(0, len(ids) - 1) for _, ids in clusters.values())
    # Occupying an empty connector can prevent the opponent joining groups.
    blocking = 0.0
    for cell in cells:
        enemy = {foe[n] for n in adjacent[cell] if n in foe}
        if len(enemy) >= 2:
            blocking += 4.0 * (len(enemy) - 1)
            blocking += min(8.0, sum(foe_sizes[k] for k in enemy) * 0.4)
    score = 0.65 * sum(base[cell] for cell in cells)
    score += 6.5 * growth + 3.0 * merge_count + blocking
    score += 1.0 * (count - 1)
    # A growing score >= the opponent's gives THEM 3 stones next turn.
    if growth and potential >= state.scores[other(state.to_move)]:
        score -= 5.0
    return score


def ranked_candidate_turns(
    state: GameState, max_branch: int = 10, max_cells: int = 12,
    full_width: bool = False, deadline: Optional[float] = None,
) -> List[Turn]:
    check_deadline(deadline)
    if state.is_game_over():
        return []
    if max_branch < 1 or max_cells < 1:
        raise ValueError("max_branch and max_cells must be positive")

    base = _cell_scores(state)
    cell_pool = (state.board.empty_cells() if full_width else
                 heapq.nlargest(max_cells, base, key=base.__getitem__))
    board_order = {cell: i for i, cell in enumerate(state.board.cells)}
    cell_pool.sort(key=board_order.__getitem__)
    limit = min(state.stones_allowed_this_turn(), len(cell_pool))
    if not limit:
        return []
    mine, mine_sizes = _component_map(state, state.to_move)
    foe, foe_sizes = _component_map(state, other(state.to_move))
    adjacent = {cell: set(neighbours(cell)) for cell in cell_pool}
    # Bounded top-K heap; one best turn per action length is tracked too.
    top = []
    best_by_length = {}
    complete = [] if full_width else None
    serial = 0
    for length in range(1, limit + 1):
        for cells in combinations(cell_pool, length):
            serial += 1
            if serial % 128 == 0:
                check_deadline(deadline)
            value = _turn_tactical_score(
                state, cells, base, mine, mine_sizes, foe, foe_sizes, adjacent,
            )
            item = (value, -serial, cells)
            if full_width:
                complete.append(item)
            else:
                if length not in best_by_length or item > best_by_length[length]:
                    best_by_length[length] = item
                if len(top) < max_branch:
                    heapq.heappush(top, item)
                elif item > top[0]:
                    heapq.heapreplace(top, item)
    if full_width:
        complete.sort(reverse=True)
        return [list(item[2]) for item in complete]

    selected = sorted(top, reverse=True)
    # Preserve tactical breadth only when the budget can represent each legal
    # action length. With max_branch=1, return the strongest scored action.
    if max_branch >= limit:
        present = {len(item[2]) for item in selected}
        for length in range(1, limit + 1):
            if length in present:
                continue
            # Replace the worst candidate from an overrepresented length.
            length_counts = {k: sum(len(v[2]) == k for v in selected)
                             for k in range(1, limit + 1)}
            drop = next((j for j in range(len(selected) - 1, -1, -1)
                         if length_counts[len(selected[j][2])] > 1), None)
            if drop is not None:
                selected[drop] = best_by_length[length]
                present.add(length)
        selected.sort(reverse=True)
    check_deadline(deadline)
    return [list(item[2]) for item in selected]
