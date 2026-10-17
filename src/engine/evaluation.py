"""Reference static evaluation from a named player's perspective.

Terminal states are decided by the official lexicographic group-size tiebreak;
nonterminal scores are estimates, NOT proven outcomes.
"""
from ..board.board import BLACK, WHITE, other
from ..board.coordinates import neighbours
from ..board.groups import group_sizes
from ..game.state import GameState

WIN_VALUE = 1_000_000.0


def _position_features(state: GameState, colour: str) -> float:
    groups = group_sizes(state.board, colour)
    largest = groups[0] if groups else 0
    second = groups[1] if len(groups) > 1 else 0
    stones = sum(groups)
    # Empty cells directly neighbouring our groups (expansion options).
    frontier = set()
    for stone in state.board.stones_of(colour):
        frontier.update(n for n in neighbours(stone) if state.board.cells[n] is None)
    return 12.0 * largest + 3.5 * second + 0.5 * stones + 0.35 * len(frontier)


def evaluate(state: GameState, colour: str) -> float:
    """Return value >0 when the position favours `colour`.

    The immediate three-stone opportunity is a tempo advantage to whichever
    player is about to move. It is not a free win, hence a small bonus.
    """
    if colour not in (WHITE, BLACK):
        raise ValueError(f"invalid colour: {colour!r}")
    opponent = other(colour)
    if state.is_game_over():
        winner = state.winner()
        if winner is None:
            return 0.0
        return WIN_VALUE if winner == colour else -WIN_VALUE

    result = _position_features(state, colour) - _position_features(state, opponent)
    if state.stones_allowed_this_turn() == 3:
        result += 5.0 if state.to_move == colour else -5.0
    return result