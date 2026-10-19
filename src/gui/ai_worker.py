"""Background AI calculation for responsive pygame game modes."""

from dataclasses import dataclass
from threading import Event, Thread
from typing import List, Optional

from ..board.coordinates import Cell
from ..engine.player import AIPlayer
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

    @property
    def busy(self) -> bool:
        return self._thread is not None

    def start(self, player: AIPlayer, live_state: GameState) -> bool:
        if self.busy:
            return False
        if live_state.to_move != player.colour or live_state.is_game_over():
            raise ValueError("AI must be the side to move")
        snapshot = live_state.copy()
        self._finished = Event()
        self._result = AIResult()
        self._discarded = False
        finished, result = self._finished, self._result

        def calculate() -> None:
            try:
                result.move = player.choose_move(snapshot)
            except BaseException as error:
                result.error = error
            finally:
                finished.set()

        self._thread = Thread(target=calculate, daemon=True, name="Catchup-AI")
        self._thread.start()
        return True

    def discard(self) -> None:
        if self.busy:
            self._discarded = True

    def poll(self) -> Optional[AIResult]:
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