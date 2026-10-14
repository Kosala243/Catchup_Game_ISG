"""
Transposition table.

SCAFFOLDING NOTE: `hash_state` below is a slow, non-incremental placeholder
(hashes the whole board every call). A real engine typically uses Zobrist
hashing, updated incrementally as stones are placed/removed. This, and the
replacement scheme, are yours to design.
"""

from typing import Any, Dict, Optional, Tuple

from ..game.state import GameState


def hash_state(state: GameState) -> int:
    """PLACEHOLDER hash - TODO: replace with incremental Zobrist hashing."""
    stones = tuple(sorted(
        (cell, colour) for cell, colour in state.board.cells.items() if colour is not None
    ))
    return hash((stones, state.to_move))


class TranspositionTable:
    def __init__(self) -> None:
        self._table: Dict[int, Tuple[int, float, Any]] = {}

    def get(self, key: int) -> Optional[Tuple[int, float, Any]]:
        """Returns (depth, value, best_move) if present."""
        return self._table.get(key)

    def store(self, key: int, depth: int, value: float, best_move: Any) -> None:
        """PLACEHOLDER: always overwrites. TODO: consider a depth-preferred replacement scheme."""
        self._table[key] = (depth, value, best_move)
