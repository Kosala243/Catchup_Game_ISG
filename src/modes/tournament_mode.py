"""Terminal tournament relay with persistent whole-game AI time allowance."""

from ..board.board import WHITE, BLACK
from ..engine.player import AIPlayer
from ..game.notation import format_turn, parse_turn
from ..game.state import GameState
from ..persistence.save_load import load_tournament_session, save_tournament_session

AUTOSAVE_PATH = "saves/current_game.json"


def run(my_colour: str, think_seconds: float = 600.0, resume: bool = False) -> None:
    if my_colour not in (WHITE, BLACK):
        raise ValueError("--colour must be W or B")
    if not (0 < think_seconds <= 600):
        raise ValueError("tournament thinking time must be in (0, 600] seconds")

    if resume:
        state, saved_clock = load_tournament_session(
            AUTOSAVE_PATH, expected_colour=my_colour, max_total_seconds=think_seconds,
        )
        ai = AIPlayer(my_colour, saved_clock.total_seconds, saved_clock.time_left())
    else:
        state = GameState()
        ai = AIPlayer(my_colour, think_seconds)

    # Records the new session immediately; after resume, also clears any
    # previously charged reservation so it cannot be charged twice.
    save_tournament_session(state, AUTOSAVE_PATH, my_colour, ai.clock)
    print(f"Playing as {my_colour}; AI time remaining: {ai.clock.time_left():.1f}s")
    print("Enter opponent turns such as E5 or D5 E6; type 'undo' to take back the last turn.")

    while not state.is_game_over():
        if state.to_move == my_colour:
            budget = ai.move_budget(state)
            # Pre-charge the worst-case move budget to disk, so a crash during
            # search cannot grant free thinking time on restart.
            reserve = min(ai.clock.time_left(), budget + max(0.02, budget * 0.02))
            save_tournament_session(
                state, AUTOSAVE_PATH, my_colour, ai.clock, reserved_seconds=reserve,
            )
            move = ai.choose_move(state)
            state.apply_turn(move)
            # Persist the move before communicating it to the opponent.
            save_tournament_session(state, AUTOSAVE_PATH, my_colour, ai.clock)
            print(f"My move: {format_turn(move)} (AI time left: {ai.clock.time_left():.1f}s)")
        else:
            raw = input(f"Opponent ({state.to_move}) move: ").strip()
            if raw.lower() == "undo":
                if not state.history:
                    print("Nothing to undo.")
                    continue
                state.undo()
                # Undo does NOT refund the AI's already-used thinking time.
                save_tournament_session(state, AUTOSAVE_PATH, my_colour, ai.clock)
                print("Last turn undone. AI thinking time is not refunded.")
                continue
            try:
                state.apply_turn(parse_turn(raw))
            except ValueError as error:
                print(f"Invalid opponent turn: {error}")
                continue
        save_tournament_session(state, AUTOSAVE_PATH, my_colour, ai.clock)

    print(f"Game over. Winner: {state.winner()}; AI time left: {ai.clock.time_left():.1f}s")