"""Human vs AI controller and pygame entry point.

One undo reverses the most recent human turn and any AI response. AI searches
run on a copy in a background worker to keep the window responsive.
"""
from typing import List

from ..board.board import BLACK, WHITE, other
from ..board.coordinates import Cell
from ..engine.player import AIPlayer
from ..game.state import GameState
from ..gui.ai_worker import AIWorker


class HumanGameController:
    def __init__(self, human_colour: str = WHITE, think_seconds: float = 600.0) -> None:
        if human_colour not in (WHITE, BLACK):
            raise ValueError("human_colour must be W or B")
        self.human_colour = human_colour
        self.think_seconds = think_seconds
        self.worker = AIWorker()
        self.reset(first=True)

    def reset(self, first: bool = False) -> None:
        self.worker.discard()
        self.state = GameState()
        self.ai = AIPlayer(other(self.human_colour), self.think_seconds)
        self.error = None
        self.last_search = None
        self.search_history = []
        self.message = "New game. White plays first." if first else "New game started."

    def can_input(self) -> bool:
        return (self.error is None and not self.state.is_game_over()
                and self.state.to_move == self.human_colour)

    def confirm_turn(self, cells: List[Cell]) -> None:
        if not self.can_input():
            raise ValueError("It is not the human player's turn")
        self.state.apply_turn(cells)
        self.message = f"You placed {len(cells)} stone(s)."

    def undo(self) -> None:
        # Rewind to BEFORE the last human action; do not undo the AI's opening
        # if Black has not yet played a human turn.
        index = next((i for i in range(len(self.state.history) - 1, -1, -1)
                      if self.state.history[i].player == self.human_colour), None)
        if index is None:
            self.message = "No human turn to undo."
            return
        self.worker.discard()
        self.last_search = None
        while len(self.state.history) > index:
            self.state.undo()
        self.error = None
        self.message = "Undid your last turn and any AI reply (time is not refunded)."

    def update(self) -> None:
        for event in self.worker.drain_progress():
            self.last_search = dict(event, side=self.ai.colour)
            self.search_history.append(self.last_search)
        outcome = self.worker.poll()
        if outcome is not None and not outcome.discarded:
            if outcome.error is not None:
                self.error = f"AI error: {outcome.error}"
            elif outcome.move is not None:
                try:
                    self.state.apply_turn(outcome.move)
                    self.message = f"AI played {len(outcome.move)} stone(s)."
                except ValueError as error:
                    self.error = f"AI returned an invalid move: {error}"
        if (not self.worker.busy and self.error is None
                and not self.state.is_game_over()
                and self.state.to_move == self.ai.colour):
            self.worker.start(self.ai, self.state)

    def diagnostics(self) -> dict:
        return {self.ai.colour: self.last_search} if self.last_search is not None else {}

    def status(self) -> str:
        if self.error:
            return self.error + "  |  Press R to restart."
        if self.state.is_game_over():
            winner = self.state.winner()
            return "Game over: Draw." if winner is None else (
                "Game over: You win!" if winner == self.human_colour else "Game over: AI wins.")
        if self.worker.busy:
            return f"AI thinking... {self.ai.clock.time_left():.1f}s remaining"
        return self.message


def run(human_colour: str = WHITE, think_seconds: float = 600.0) -> None:
    from ..gui.app import GuiApp

    from ..gui.turn_clock import TurnClock

    controller = HumanGameController(human_colour, think_seconds)
    human_clock = TurnClock(think_seconds)

    def sync_clock():
        human_clock.sync(controller.can_input())

    def confirm(cells):
        controller.confirm_turn(cells)
        sync_clock()

    def undo():
        controller.undo()
        sync_clock()

    def restart():
        controller.reset()
        human_clock.reset(think_seconds)
        sync_clock()

    def frame():
        controller.update()
        sync_clock()

    def clock_values():
        return {
            human_colour: (human_clock.time_left(), human_clock.is_running),
            other(human_colour): (controller.ai.clock.time_left(),
                                  controller.ai.clock.is_running),
        }

    sync_clock()
    app = GuiApp(
        controller.state, confirm, undo,
        on_restart=restart, on_frame=frame,
        state_provider=lambda: controller.state,
        input_enabled=controller.can_input, status_provider=controller.status,
        clock_provider=clock_values,
        search_provider=controller.diagnostics,
        heading=f"Catchup | You: {'White' if human_colour == WHITE else 'Black'}",
    )
    try:
        while app.run_once():
            pass
    finally:
        controller.worker.discard()
        app.quit()
