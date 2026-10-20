"""Background AI calculation for responsive pygame game modes.

Only the UI thread may mutate the live GameState. Worker threads receive a
copy and return a complete turn. Discarded searches are allowed to finish,
so their AI think time is still charged and their results are never applied.
"""
from dataclasses import dataclass
from threading import Event, Thread
from queue import SimpleQueue, Empty
from typing import List, Optional

from ..board.coordinates import Cell
from ..engine.player import AIPlayer
from ..engine.search import capture_search_progress
from ..game.state import GameState


@dataclass
class AIResult:
    move: Optional[List[Cell]] = None
    error: Optional[BaseException] = None
    discarded: bool = False


class AIWorker:
    def __init__(self) -> None:
        self._thread: Optional[Thread] = None
        self._finished: Optional[Event] = None
        self._result: Optional[AIResult] = None
        self._discarded = False
        self._progress = SimpleQueue()

    @property
    def busy(self) -> bool:
        return self._thread is not None

    def start(self, player: AIPlayer, live_state: GameState) -> bool:
        """Start when idle; never search the mutable state shown by the UI."""
        if self.busy:
            return False
        if live_state.to_move != player.colour or live_state.is_game_over():
            raise ValueError("AI must be the side to move")
        snapshot = live_state.copy()
        self._finished = Event()
        self._result = AIResult()
        self._discarded = False
        self._progress = SimpleQueue()
        finished, result = self._finished, self._result
        events = self._progress

        def calculate() -> None:
            try:
                with capture_search_progress(events.put):
                    result.move = player.choose_move(snapshot)
            except BaseException as error:
                result.error = error
            finally:
                finished.set()

        self._thread = Thread(target=calculate, daemon=True, name="Catchup-AI")
        self._thread.start()
        return True

    def discard(self) -> None:
        """Ignore the pending result after undo/restart (without refunding time)."""
        if self.busy:
            self._discarded = True

    def drain_progress(self) -> list[dict]:
        """Read worker-generated immutable search reports from the UI thread."""
        result = []
        while True:
            try:
                event = self._progress.get_nowait()
            except Empty:
                break
            if not self._discarded:
                result.append(event)
        return result

    def poll(self) -> Optional[AIResult]:
        """Return exactly one result, on completion; otherwise return None."""
        if not self.busy or not self._finished.is_set():
            return None
        self._thread.join(timeout=0)
        result = self._result
        result.discarded = self._discarded
        self._thread = None
        self._finished = None
        self._result = None
        self._discarded = False
        return result
