"""Responsive pygame board and controls, shared by human and visual AI modes.

Rendering and input run on the main thread. The controllers handle AI searches
through AIWorker and exclusively own the live GameState.
"""
from typing import Callable, List, Optional

import pygame

from ..board.board import BLACK, WHITE
from ..board.coordinates import Cell
from ..game.state import GameState
from .hex_renderer import draw_board
from .layout import pixel_to_hex

WINDOW_SIZE = (1000, 780)
HEX_SIZE = 34
ORIGIN = (500, 410)


class GuiApp:
    def __init__(
        self,
        state: GameState,
        on_turn_confirmed: Callable[[List[Cell]], None],
        on_undo: Callable[[], None],
        *,
        on_restart: Optional[Callable[[], None]] = None,
        on_pause: Optional[Callable[[], None]] = None,
        on_frame: Optional[Callable[[], None]] = None,
        state_provider: Optional[Callable[[], GameState]] = None,
        input_enabled: Optional[Callable[[], bool]] = None,
        status_provider: Optional[Callable[[], str]] = None,
        heading: str = "Catchup",
    ) -> None:
        pygame.init()
        pygame.display.set_caption(heading)
        self.screen = pygame.display.set_mode(WINDOW_SIZE)
        self.font = pygame.font.SysFont("arial", 16)
        self.small_font = pygame.font.SysFont("arial", 14)
        self.title_font = pygame.font.SysFont("arial", 26, bold=True)
        self.clock = pygame.time.Clock()
        self._state_provider = state_provider or (lambda: state)
        self.on_turn_confirmed = on_turn_confirmed
        self.on_undo = on_undo
        self.on_restart = on_restart
        self.on_pause = on_pause
        self.on_frame = on_frame
        self.input_enabled = input_enabled or (lambda: True)
        self.status_provider = status_provider or (lambda: "")
        self.heading = heading
        self.pending: List[Cell] = []
        self.notice = ""
        self.running = True

    @property
    def state(self) -> GameState:
        return self._state_provider()

    def _can_place(self) -> bool:
        return self.input_enabled() and not self.state.is_game_over()

    def _confirm_turn(self) -> None:
        if not self.pending or not self._can_place():
            return
        try:
            self.on_turn_confirmed(list(self.pending))
        except (ValueError, IndexError) as error:
            self.notice = f"Move rejected: {error}"
            return
        self.pending.clear()
        self.notice = ""

    def _handle_cell_click(self, pos) -> None:
        if not self._can_place():
            return
        cell = pixel_to_hex(pos, HEX_SIZE, ORIGIN)
        if cell is None or not self.state.board.is_empty(cell) or cell in self.pending:
            return
        self.pending.append(cell)
        if len(self.pending) == self.state.stones_allowed_this_turn():
            self._confirm_turn()

    def _actions(self):
        return [
            ("Confirm", bool(self.pending) and self._can_place(), self._confirm_turn),
            ("Clear", bool(self.pending), self._clear),
            ("Undo (U)", self.on_undo is not None, self._undo),
            ("Restart (R)", self.on_restart is not None, self._restart),
            ("Pause (Space)", self.on_pause is not None, self._pause),
        ]

    def _clear(self) -> None:
        self.pending.clear()
        self.notice = "Selection cleared."

    def _undo(self) -> None:
        self.pending.clear()
        if self.on_undo:
            self.on_undo()
        self.notice = ""

    def _restart(self) -> None:
        self.pending.clear()
        if self.on_restart:
            self.on_restart()
        self.notice = ""

    def _pause(self) -> None:
        if self.on_pause:
            self.on_pause()

    def _handle_event(self, event) -> None:
        if event.type == pygame.QUIT:
            self.running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN:
                self._confirm_turn()
            elif event.key in (pygame.K_BACKSPACE, pygame.K_ESCAPE):
                if self.pending:
                    self.pending.pop()
            elif event.key == pygame.K_u:
                self._undo()
            elif event.key == pygame.K_r:
                self._restart()
            elif event.key == pygame.K_SPACE:
                self._pause()
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 3:
                if self.pending:
                    self.pending.pop()
                return
            if event.button != 1:
                return
            buttons = self._button_rects()
            for (label, enabled, action), rectangle in zip(self._actions(), buttons):
                if rectangle.collidepoint(event.pos):
                    if enabled:
                        action()
                    return
            self._handle_cell_click(event.pos)

    @staticmethod
    def _button_rects():
        return [pygame.Rect(120 + i * 158, 700, 148, 44) for i in range(5)]

    def _label(self, message: str, font, colour, x: int, y: int) -> None:
        # Prevent long error messages overflowing beyond the window edge.
        while len(message) > 6 and font.size(message)[0] > WINDOW_SIZE[0] - x - 20:
            message = message[:-2]
        if message != "" and not message.endswith("...") and font.size(message)[0] > WINDOW_SIZE[0] - x - 20:
            message += "..."
        self.screen.blit(font.render(message, True, colour), (x, y))

    def _render(self) -> None:
        state = self.state
        draw_board(self.screen, state.board, HEX_SIZE, ORIGIN, self.small_font,
                   highlight_cells=self.pending)
        pygame.draw.rect(self.screen, (235, 242, 247), pygame.Rect(0, 0, 1000, 105))
        self._label(self.heading, self.title_font, (25, 43, 65), 22, 12)
        score_line = (f"To move: {'White' if state.to_move == WHITE else 'Black'}"
                      f"  |  Largest groups: W {state.scores[WHITE]}, B {state.scores[BLACK]}"
                      f"  |  Empty: {len(state.board.empty_cells())}")
        self._label(score_line, self.font, (35, 53, 69), 22, 47)
        status = self.notice or self.status_provider()
        self._label(status, self.small_font, (45, 66, 83), 22, 77)

        pygame.draw.rect(self.screen, (235, 242, 247), pygame.Rect(0, 686, 1000, 94))
        for (label, enabled, _), rectangle in zip(self._actions(), self._button_rects()):
            fill = (52, 95, 130) if enabled else (163, 177, 186)
            pygame.draw.rect(self.screen, fill, rectangle, border_radius=8)
            rendered = self.small_font.render(label, True, (255, 255, 255))
            self.screen.blit(rendered, rendered.get_rect(center=rectangle.center))
        if not state.is_game_over() and self._can_place():
            hint = (f"Select up to {state.stones_allowed_this_turn()} empty cell(s); "
                    "Enter commits early, Backspace removes selection")
        elif state.is_game_over():
            winner = state.winner()
            hint = "Game finished: Draw" if winner is None else f"Game finished: {'White' if winner == WHITE else 'Black'} wins"
        else:
            hint = "AI controls this turn. U = undo, R = restart, Space = pause in AI-vs-AI."
        self._label(hint, self.small_font, (35, 53, 69), 20, 755)
        pygame.display.flip()

    def run_once(self) -> bool:
        for event in pygame.event.get():
            self._handle_event(event)
        if self.running and self.on_frame is not None:
            self.on_frame()
        if self.running:
            self._render()
        self.clock.tick(30)
        return self.running

    def quit(self) -> None:
        pygame.quit()