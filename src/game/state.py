"""Catchup game state with atomic turn validation, copy, and undo."""

from dataclasses import dataclass
from typing import Dict, List, Optional

from . import rules
from ..board.board import BLACK, WHITE, Board, other
from ..board.coordinates import Cell
from ..board.groups import group_sizes, largest_group_size

Turn = List[Cell]


@dataclass
class HistoryEntry:
    player: str
    cells: Turn
    scores_before: Dict[str, int]
    opponent_score_increased_before: bool


class GameState:
    def __init__(self) -> None:
        self.board = Board()
        self.scores: Dict[str, int] = {WHITE: 1, BLACK: 1}
        self.to_move: str = WHITE
        self.score_increased_last_turn: bool = False
        self.is_opening_move: bool = True
        self.history: List[HistoryEntry] = []

    def copy(self) -> "GameState":
        """Independent copy, including undo history (no shared mutable lists/dicts)."""
        result = GameState()
        result.board = self.board.copy()
        result.scores = dict(self.scores)
        result.to_move = self.to_move
        result.score_increased_last_turn = self.score_increased_last_turn
        result.is_opening_move = self.is_opening_move
        result.history = [
            HistoryEntry(
                player=entry.player,
                cells=list(entry.cells),
                scores_before=dict(entry.scores_before),
                opponent_score_increased_before=entry.opponent_score_increased_before,
            )
            for entry in self.history
        ]
        return result

    def stones_allowed_this_turn(self) -> int:
        if self.is_opening_move:
            return 1
        return rules.max_stones_allowed(
            mover_score=self.scores[self.to_move],
            opponent_score=self.scores[other(self.to_move)],
            opponent_score_increased=self.score_increased_last_turn,
        )

    def legal_cell_choices(self) -> List[Cell]:
        return self.board.empty_cells()

    def apply_turn(self, cells: Turn) -> None:
        """Apply a complete turn or reject it without changing any state."""
        if self.is_game_over():
            raise ValueError("the game is already over")

        chosen = list(cells)
        colour = self.to_move
        max_allowed = self.stones_allowed_this_turn()
        if not (1 <= len(chosen) <= max_allowed):
            raise ValueError(
                f"{colour} may place 1..{max_allowed} stones this turn, got {len(chosen)}"
            )
        try:
            if len(set(chosen)) != len(chosen):
                raise ValueError("duplicate cell in the same turn")
        except TypeError as error:
            raise ValueError("turn cells must be hashable coordinate pairs") from error

        # Prevalidate *every* placement before adding history or placing stones.
        for cell in chosen:
            if cell not in self.board.cells:
                raise ValueError(f"invalid Catchup cell: {cell!r}")
            if not self.board.is_empty(cell):
                raise ValueError(f"cell {cell!r} is already occupied")

        self.history.append(
            HistoryEntry(
                player=colour,
                cells=chosen,
                scores_before=dict(self.scores),
                opponent_score_increased_before=self.score_increased_last_turn,
            )
        )
        for cell in chosen:
            self.board.place(cell, colour)

        new_score = largest_group_size(self.board, colour)
        self.score_increased_last_turn = new_score > self.scores[colour]
        self.scores[colour] = new_score
        self.is_opening_move = False
        self.to_move = other(colour)

    def undo(self) -> None:
        if not self.history:
            raise IndexError("nothing to undo")
        entry = self.history.pop()
        for cell in entry.cells:
            self.board.remove(cell)
        self.scores = dict(entry.scores_before)
        self.score_increased_last_turn = entry.opponent_score_increased_before
        self.to_move = entry.player
        self.is_opening_move = len(self.history) == 0

    def is_game_over(self) -> bool:
        return self.board.is_full()

    def winner(self) -> Optional[str]:
        """Winner at a terminal state: W, B, or None for a draw."""
        if not self.is_game_over():
            raise ValueError("winner is defined only when the board is full")
        result = rules.compare_group_lists(
            group_sizes(self.board, WHITE), group_sizes(self.board, BLACK)
        )
        if result > 0:
            return WHITE
        if result < 0:
            return BLACK
        return None