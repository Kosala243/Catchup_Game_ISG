"""Collision-free incremental bitboard keys and depth-preferred alpha-beta table.

A 61-cell board fits in two Python integers. Unlike a 64-bit Zobrist hash,
these keys are exact: different boards never collide. This also avoids reliance
on Python's salted hash() across processes. No changes to GameState are needed.
"""
from collections import OrderedDict
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

from ..board.board import WHITE, BLACK
from ..board.coordinates import Cell, all_cells
from ..game.state import GameState, Turn

CELL_BITS = {cell: 1 << i for i, cell in enumerate(all_cells())}

# Occupancy, side to move, Catchup bonus-turn state, current scores,
# search perspective and selective move generation settings all matter.
PositionKey = Tuple[int, int, str, bool, bool, int, int, str, int, int, bool, int, int, int, str]


def occupancy_bits(state: GameState) -> Tuple[int, int]:
    """Compute exact masks once at the root; child masks can be updated with OR."""
    white = black = 0
    for cell, colour in state.board.cells.items():
        if colour == WHITE:
            white |= CELL_BITS[cell]
        elif colour == BLACK:
            black |= CELL_BITS[cell]
    return white, black


def turn_mask(turn: Turn) -> int:
    """The occupied bit positions of a complete 1-, 2-, or 3-stone turn."""
    result = 0
    for cell in turn:
        result |= CELL_BITS[cell]
    return result


def position_key(
    state: GameState, perspective: str, max_branch: int, max_cells: int,
    full_width: bool, masks: Optional[Tuple[int, int]] = None,
    endgame_full_width_cells: int = 7,
    extensions_left: int = 0,
    extension_growth: int = 3,
    evaluation_id: str = "full",
) -> PositionKey:
    """Position identifier including the fields relevant to turn legality/search."""
    white, black = occupancy_bits(state) if masks is None else masks
    return (white, black, state.to_move, state.score_increased_last_turn,
            state.is_opening_move, state.scores[WHITE], state.scores[BLACK],
            perspective, max_branch, max_cells, full_width, endgame_full_width_cells,
            extensions_left, extension_growth, evaluation_id)


class Bound(Enum):
    EXACT = "exact"
    LOWER = "lower"
    UPPER = "upper"


@dataclass(frozen=True)
class TTEntry:
    depth: int
    value: float
    bound: Bound
    best_move: Optional[Tuple[Cell, ...]]


class TranspositionTable:
    """Bounded FIFO store; deeper entries are preferred for the same key.

    FIFO avoids unbounded growth in long games; replacing a key doesn't change
    its insertion order. This is a reference implementation, not a final tuning.
    """
    def __init__(self, max_entries: int = 50_000) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        self.max_entries = max_entries
        self._entries: OrderedDict[PositionKey, TTEntry] = OrderedDict()

    def __len__(self) -> int:
        return len(self._entries)

    def get(self, key: PositionKey) -> Optional[TTEntry]:
        return self._entries.get(key)

    def store(self, key: PositionKey, entry: TTEntry) -> bool:
        previous = self._entries.get(key)
        if previous is not None:
            if previous.depth > entry.depth:
                return False
            # For the same depth, an exact result is more useful than a bound.
            if previous.depth == entry.depth and previous.bound == Bound.EXACT and entry.bound != Bound.EXACT:
                return False
            self._entries[key] = entry
            return True
        if len(self._entries) >= self.max_entries:
            self._entries.popitem(last=False)
        self._entries[key] = entry
        return True

    def clear(self) -> None:
        self._entries.clear()
