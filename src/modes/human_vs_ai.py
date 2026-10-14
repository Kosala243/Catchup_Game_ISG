"""
Local human-vs-AI play, using the pygame GUI. Handy for your own testing and
for the demo segment of the video.
"""

from ..board.board import BLACK, WHITE
from ..engine.player import AIPlayer
from ..game.state import GameState
from ..gui.app import GuiApp


def run(human_colour: str = WHITE, think_seconds: float = 600.0) -> None:
    state = GameState()
    ai_colour = BLACK if human_colour == WHITE else WHITE
    ai = AIPlayer(colour=ai_colour, total_seconds=think_seconds)

    def on_turn_confirmed(cells):
        state.apply_turn(cells)

    def on_undo():
        if state.history:
            state.undo()

    app = GuiApp(state, on_turn_confirmed, on_undo)
    while app.run_once():
        if not state.is_game_over() and state.to_move == ai.colour:
            move = ai.choose_move(state)
            state.apply_turn(move)
    app.quit()
