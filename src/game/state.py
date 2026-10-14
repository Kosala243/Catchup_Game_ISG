"""
GameState: board + scores + turn bookkeeping, with undo support.

SCAFFOLDING NOTE: this is the "state-action representation" the assignment
asks you to design and own. It's provided here as a working placeholder so
the rest of the project runs; review it, adjust it to fit your search
engine, and disclose in AI_USAGE.md if you keep parts of it.
"""

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
        # Did `to_move`'s opponent's score increase on the turn they just took?
        # Drives the "up to three stones" rule. White's opening placement does
        # not count (per the rules PDF remark), so this starts False.
        self.score_increased_last_turn: bool = False
        self.is_opening_move: bool = True
        self.history: List[HistoryEntry] = []

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
        colour = self.to_move
        max_allowed = self.stones_allowed_this_turn()
        if not (1 <= len(cells) <= max_allowed):
            raise ValueError(f"{colour} may place 1..{max_allowed} stones this turn, got {len(cells)}")
        if len(set(cells)) != len(cells):
            raise ValueError("duplicate cell in the same turn")

        self.history.append(HistoryEntry(
            player=colour,
            cells=list(cells),
            scores_before=dict(self.scores),
            opponent_score_increased_before=self.score_increased_last_turn,
        ))

        for cell in cells:
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
        self.scores = entry.scores_before
        self.score_increased_last_turn = entry.opponent_score_increased_before
        self.to_move = entry.player
        self.is_opening_move = len(self.history) == 0

    def is_game_over(self) -> bool:
        return self.board.is_full()

    def winner(self) -> Optional[str]:
        """Returns WHITE, BLACK, or None for a draw. Only meaningful once is_game_over()."""
        result = rules.compare_group_lists(
            group_sizes(self.board, WHITE), group_sizes(self.board, BLACK)
        )
        if result > 0:
            return WHITE
        if result < 0:
            return BLACK
        return None
