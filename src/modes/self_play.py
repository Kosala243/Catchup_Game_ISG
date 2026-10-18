"""Visual AI vs AI replay with pause, undo and restart controls."""
import time
from typing import List

from ..board.board import BLACK, WHITE
from ..board.coordinates import Cell
from ..engine.player import AIPlayer
from ..game.state import GameState
from ..gui.ai_worker import AIResult, AIWorker


class VisualSelfPlayController:
    def __init__(self, think_seconds: float = 600.0, delay_ms: int = 400) -> None:
        if delay_ms < 0:
            raise ValueError("delay_ms must be nonnegative")
        self.think_seconds = think_seconds
        self.delay_seconds = delay_ms / 1000.0
        self.worker = AIWorker()
        self.reset(first=True)

    def reset(self, first: bool = False) -> None:
        self.worker.discard()
        self.state = GameState()
        self.players = {
            WHITE: AIPlayer(WHITE, self.think_seconds),
            BLACK: AIPlayer(BLACK, self.think_seconds),
        }
        self.pending: AIResult | None = None
        self.paused = False
        self.error = None
        self.next_at = time.monotonic() + self.delay_seconds
        self.message = "New visual self-play game." if first else "Self-play restarted."

    def confirm_turn(self, cells: List[Cell]) -> None:
        raise ValueError("Manual stone placement is disabled in AI vs AI mode")

    def toggle_pause(self) -> None:
        self.paused = not self.paused
        self.message = "Paused." if self.paused else "Resumed."

    def undo(self) -> None:
        self.worker.discard()
        self.pending = None
        if self.state.history:
            self.state.undo()
            self.error = None
            self.message = "Last AI turn undone. Clock time is not refunded."
            self.next_at = time.monotonic() + self.delay_seconds
            # Remain paused, allowing inspection before continuing.
            self.paused = True
        else:
            self.message = "No turn to undo."

    def update(self) -> None:
        outcome = self.worker.poll()
        if outcome is not None and not outcome.discarded:
            self.pending = outcome
        if self.error is not None or self.paused or self.state.is_game_over():
            return
        if self.pending is not None:
            result, self.pending = self.pending, None
            if result.error is not None:
                self.error = f"AI error: {result.error}"
                return
            try:
                self.state.apply_turn(result.move)
            except (TypeError, ValueError) as error:
                self.error = f"Invalid AI move: {error}"
                return
            self.message = f"{self.state.history[-1].player} played {len(result.move)} stone(s)."
            self.next_at = time.monotonic() + self.delay_seconds
        if (not self.worker.busy and self.pending is None
                and not self.state.is_game_over()
                and time.monotonic() >= self.next_at):
            self.worker.start(self.players[self.state.to_move], self.state)

    def status(self) -> str:
        if self.error:
            return self.error + " | Press R to restart."
        if self.state.is_game_over():
            winner = self.state.winner()
            return f"Game over: {'Draw' if winner is None else winner + ' wins'}"
        if self.paused:
            return "PAUSED | Space to resume, U to undo, R to restart."
        if self.worker.busy:
            player = self.players[self.state.to_move]
            return f"AI {player.colour} thinking... {player.clock.time_left():.1f}s remaining"
        return self.message


def run(think_seconds: float = 600.0, delay_ms: int = 400) -> None:
    from ..gui.app import GuiApp

    controller = VisualSelfPlayController(think_seconds, delay_ms)
    app = GuiApp(
        controller.state, controller.confirm_turn, controller.undo,
        on_restart=controller.reset, on_frame=controller.update,
        on_pause=controller.toggle_pause, state_provider=lambda: controller.state,
        input_enabled=lambda: False, status_provider=controller.status,
        heading="Catchup | AI vs AI",
    )
    try:
        while app.run_once():
            pass
    finally:
        controller.worker.discard()
        app.quit()