"""Terminal tournament relay with recoverable clock and corrected undo handling.

The operator only records opponent moves. 'undo' reverses the *previous
opponent entry and the AI response* (not just the latest AI move).
"""
from ..board.board import WHITE, BLACK
from ..engine.player import AIPlayer
from ..game.notation import format_turn, parse_turn
from ..game.state import GameState
from ..persistence.save_load import load_tournament_session, save_tournament_session

AUTOSAVE_PATH = "saves/current_game.json"


def undo_last_exchange(state: GameState, my_colour: str) -> bool:
    """Undo the last opponent move plus its AI response, if available."""
    if len(state.history) < 2:
        return False
    if state.history[-1].player != my_colour or state.history[-2].player == my_colour:
        return False
    state.undo()
    state.undo()
    return True


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

    def checkpoint(reserved_seconds: float = 0.0) -> None:
        save_tournament_session(state, AUTOSAVE_PATH, my_colour, ai.clock,
                                reserved_seconds=reserved_seconds)

    checkpoint()
    print(f"Playing as {my_colour}. AI time remaining: {ai.clock.time_left():.1f}s")
    print("Commands: E5 or D5 E6 (opponent move), undo, status, help, quit")

    while not state.is_game_over():
        if state.to_move == my_colour:
            budget = ai.move_budget(state)
            reserve = min(ai.clock.time_left(), budget + max(0.02, budget * 0.02))
            checkpoint(reserved_seconds=reserve)
            move = ai.choose_move(state)
            state.apply_turn(move)
            # Save before printing so restart never repeats a communicated move.
            checkpoint()
            print(f"My move: {format_turn(move)} (AI time: {ai.clock.time_left():.1f}s left)")
            continue

        try:
            raw = input(f"Opponent ({state.to_move}) move: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nSession saved. Restart using --resume.")
            return
        command = raw.lower()
        if command == "quit":
            checkpoint()
            print("Session saved. Restart using --resume.")
            return
        if command == "help":
            print("Enter 1-3 cell labels separated by spaces. undo corrects the previous "
                  "opponent entry and AI response. status shows scores and clock.")
            continue
        if command == "status":
            print(f"Turn: {state.to_move}; scores: W={state.scores[WHITE]} "
                  f"B={state.scores[BLACK]}; AI remaining: {ai.clock.time_left():.1f}s")
            continue
        if command == "undo":
            if undo_last_exchange(state, my_colour):
                checkpoint()
                print("Previous opponent turn and AI reply undone; AI time NOT refunded.")
            else:
                print("No complete opponent+AI exchange to undo.")
            continue
        try:
            state.apply_turn(parse_turn(raw))
        except ValueError as error:
            print(f"Invalid opponent turn: {error}")
            continue
        checkpoint()

    print(f"Game over. Winner: {state.winner()}; AI time left: {ai.clock.time_left():.1f}s")