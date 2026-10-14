from src.engine import search
from src.game.state import GameState


def test_placeholder_choose_move_is_legal():
    state = GameState()
    move = search.choose_move(state, time_budget_seconds=1.0)
    assert len(move) == 1  # White's opening move must be exactly one stone
    state.apply_turn(move)

    move2 = search.choose_move(state, time_budget_seconds=1.0)
    assert 1 <= len(move2) <= state.stones_allowed_this_turn()
