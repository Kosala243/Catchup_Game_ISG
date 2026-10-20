"""Responsive pygame board and controls, shared by human and visual AI modes.

Rendering and input run on the main thread. The controllers handle AI searches
through AIWorker and exclusively own the live GameState.
"""
from typing import Callable, List, Optional

import math
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
        clock_provider: Optional[Callable[[], dict]] = None,
        search_provider: Optional[Callable[[], dict]] = None,
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
        self.clock_provider = clock_provider or (lambda: {})
        self.search_provider = search_provider or (lambda: {})
        self.show_diagnostics = True
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
            elif event.key == pygame.K_d:
                self.show_diagnostics = not self.show_diagnostics
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

    def _draw_game_clocks(self) -> None:
        """Draw live, independent clocks without changing engine accounting.

        Provider format: {"W": (seconds_left, running), "B": (...)}.
        An idle clock stays frozen; only the currently searching AI runs.
        """
        clocks = self.clock_provider()
        if not clocks:
            return
        for i, colour in enumerate((WHITE, BLACK)):
            if colour not in clocks:
                continue
            seconds, running = clocks[colour]
            seconds = max(0.0, float(seconds))
            # Tenths of seconds let short AI moves visibly change the clock.
            shown_tenths = max(0, int(seconds * 10))
            mins, deci = divmod(shown_tenths, 600)
            secs, tenth = divmod(deci, 10)
            remaining = f"{mins:02d}:{secs:02d}.{tenth}"
            left = 520 + 235 * i
            rect = pygame.Rect(left, 9, 220, 34)
            background = (221, 244, 231) if running else (225, 232, 240)
            if seconds <= 10:
                background = (255, 216, 216)
            pygame.draw.rect(self.screen, background, rect, border_radius=7)
            pygame.draw.rect(self.screen, (67, 110, 84) if running else
                             (145, 156, 168), rect, 2, border_radius=7)
            caption = f"{'White' if colour == WHITE else 'Black'}  {remaining}"
            if running:
                caption += "  >"
            ink = (141, 26, 30) if seconds <= 10 else (21, 45, 65)
            label = self.font.render(caption, True, ink)
            self.screen.blit(label, label.get_rect(center=rect.center))

    def _draw_diagnostics(self) -> None:
        """Display only actual completed-depth events from the current game."""
        if not self.show_diagnostics:
            return
        data = self.search_provider()
        rect = pygame.Rect(776, 122, 212, 515)
        pygame.draw.rect(self.screen, (241, 246, 250), rect, border_radius=9)
        pygame.draw.rect(self.screen, (172, 190, 204), rect, 1, border_radius=9)
        heading = self.font.render("LIVE AI SEARCH   [D]", True, (23, 53, 75))
        self.screen.blit(heading, (rect.x + 10, rect.y + 10))
        y = rect.y + 42
        for side in (WHITE, BLACK):
            row = data.get(side)
            caption = ("WHITE" if side == WHITE else "BLACK") + " AI"
            self.screen.blit(self.font.render(caption, True, (27, 77, 108)), (rect.x + 10, y))
            y += 23
            if row is None:
                lines = ["No completed search yet"]
            else:
                count = row.get("total", {})
                lines = [
                    "Completed depth: " + str(row.get("depth", "?")),
                    "Best: " + str(row.get("best_turn", "?")),
                    "Eval: " + f'{row.get("evaluation", 0):+.2f}',
                    "Nodes (total): " + str(count.get("nodes", 0)),
                    "Cutoffs total: " + str(count.get("cutoffs", 0)),
                    "TT hits/stores: " + str(count.get("tt_hits", 0)) + "/" + str(count.get("tt_stores", 0)),
                    "TT size: " + str(row.get("tt_size", 0)),
                    "Extensions: " + str(count.get("tactical_extensions", 0)),
                    "Ordering/TT: " + ("ON" if row.get("use_ordering") else "OFF") + "/" + ("ON" if row.get("use_tt") else "OFF"),
                ]
            for item in lines:
                label = self.small_font.render(item, True, (45, 67, 87))
                self.screen.blit(label, (rect.x + 12, y))
                y += 20
            y += 12
        foot = self.small_font.render("Last completed depth only", True, (97, 111, 125))
        self.screen.blit(foot, (rect.x + 10, rect.bottom - 25))

    def _render(self) -> None:
        state = self.state
        draw_board(self.screen, state.board, HEX_SIZE, ORIGIN, self.small_font,
                   highlight_cells=self.pending)
        pygame.draw.rect(self.screen, (235, 242, 247), pygame.Rect(0, 0, 1000, 105))
        self._label(self.heading, self.title_font, (25, 43, 65), 22, 12)
        self._draw_game_clocks()
        self._draw_diagnostics()
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
