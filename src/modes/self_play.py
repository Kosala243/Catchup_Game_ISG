"""
Headless AI-vs-AI games, for testing and the experiments in experiments/.
"""

from ..board.board import BLACK, WHITE
from ..engine.player import AIPlayer
from ..game.state import GameState


def play_one_game(think_seconds: float = 600.0) -> dict:
    state = GameState()
    players = {WHITE: AIPlayer(WHITE, think_seconds), BLACK: AIPlayer(BLACK, think_seconds)}

    turns = 0
    while not state.is_game_over():
        move = players[state.to_move].choose_move(state)
        state.apply_turn(move)
        turns += 1

    return {
        "winner": state.winner(),
        "final_scores": dict(state.scores),
        "turns": turns,
        "white_time_left": players[WHITE].clock.time_left(),
        "black_time_left": players[BLACK].clock.time_left(),
    }


if __name__ == "__main__":
    result = play_one_game()
    print(result)
