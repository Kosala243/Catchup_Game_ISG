"""
Minimal pygame front-end: click empty cells to build a turn, buttons to
confirm/undo/restart. Used by human_vs_ai and tournament modes.

This module is plumbing (I/O and rendering), not part of the restricted
search/evaluation/state-action code.
"""

from typing import Callable, List

import pygame

from ..board.board import BLACK, WHITE
from ..board.coordinates import Cell
from ..game.state import GameState
from .hex_renderer import draw_board
from .layout import pixel_to_hex

WINDOW_SIZE = (900, 700)
HEX_SIZE = 38
ORIGIN = (WINDOW_SIZE[0] / 2, WINDOW_SIZE[1] / 2)


class GuiApp:
    def __init__(self, state: GameState, on_turn_confirmed: Callable[[List[Cell]], None],
                 on_undo: Callable[[], None]) -> None:
        pygame.init()
        pygame.display.set_caption("Catchup")
        self.screen = pygame.display.set_mode(WINDOW_SIZE)
        self.font = pygame.font.SysFont("arial", 14)
        self.clock = pygame.time.Clock()
        self.state = state
        self.on_turn_confirmed = on_turn_confirmed
        self.on_undo = on_undo
        self.pending: List[Cell] = []
        self.running = True

    def _handle_click(self, pos) -> None:
        cell = pixel_to_hex(pos, HEX_SIZE, ORIGIN)
        if cell is None or not self.state.board.is_empty(cell) or cell in self.pending:
            return
        self.pending.append(cell)
        max_allowed = self.state.stones_allowed_this_turn()
        if len(self.pending) >= max_allowed:
            self._confirm_turn()

    def _confirm_turn(self) -> None:
        if self.pending:
            self.on_turn_confirmed(list(self.pending))
            self.pending = []

    def run_once(self) -> bool:
        """Process one frame of events/rendering. Returns False when the window closed."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.MOUSEBUTTONDOWN:
                self._handle_click(event.pos)
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_RETURN and self.pending:
                    self._confirm_turn()
                elif event.key == pygame.K_u:
                    self.pending = []
                    self.on_undo()

        draw_board(self.screen, self.state.board, HEX_SIZE, ORIGIN, self.font, highlight_cells=self.pending)
        status = f"To move: {self.state.to_move}   White {self.state.scores[WHITE]} - Black {self.state.scores[BLACK]}"
        label = self.font.render(status, True, (20, 20, 20))
        self.screen.blit(label, (10, 10))
        pygame.display.flip()
        self.clock.tick(30)
        return self.running

    def quit(self) -> None:
        pygame.quit()
