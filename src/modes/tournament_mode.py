"""
Tournament mode: this program plays one colour, the operator types in the
opponent's moves as read off their screen, and this program's own moves are
printed so you can relay them back. Autosaves after every turn so a crash can
be resumed (per the tournament rules).
"""

from ..engine.player import AIPlayer
from ..game.notation import format_turn, parse_turn
from ..game.state import GameState
from ..persistence.save_load import load_game, save_game

AUTOSAVE_PATH = "saves/current_game.json"


def run(my_colour: str, think_seconds: float = 600.0, resume: bool = False) -> None:
    state = load_game(AUTOSAVE_PATH) if resume else GameState()
    ai = AIPlayer(colour=my_colour, total_seconds=think_seconds)

    print(f"Playing as {my_colour}. Type 'undo' to take back the last turn.")
    while not state.is_game_over():
        if state.to_move == my_colour:
            move = ai.choose_move(state)
            state.apply_turn(move)
            print(f"My move: {format_turn(move)}")
        else:
            raw = input(f"Opponent ({state.to_move}) move: ")
            if raw.strip().lower() == "undo":
                state.undo()
                continue
            state.apply_turn(parse_turn(raw))
        save_game(state, AUTOSAVE_PATH)

    print(f"Game over. Winner: {state.winner()}")
