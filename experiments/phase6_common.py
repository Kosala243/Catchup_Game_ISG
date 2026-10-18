"""Shared reproducible fixtures for Phase 6 experiments.

Development/test harness only: does not alter the game engine or rules.
Run experiment modules from the repository root using ``python -m experiments.NAME``.
"""
from dataclasses import dataclass
import random
from typing import Tuple

from src.game.state import GameState


@dataclass(frozen=True)
class SearchConfig:
    name: str
    use_tt: bool
    use_ordering: bool


CONFIGS = (
    SearchConfig("baseline", False, False),
    SearchConfig("tt_only", True, False),
    SearchConfig("ordering_only", False, True),
    SearchConfig("tt_and_ordering", True, True),
)


def find_config(name: str) -> SearchConfig:
    for config in CONFIGS:
        if config.name == name:
            return config
    raise ValueError(f"Unknown config {name!r}; expected: {', '.join(c.name for c in CONFIGS)}")


def build_position(seed: int, empty_cells: int) -> GameState:
    """Reconstruct a legal position using a seeded sequence of legal turns.

    Each turn uses as many stones as allowed without passing ``empty_cells``.
    This is NOT a random sample of uniformly distributed legal positions.
    """
    if isinstance(empty_cells, bool) or not isinstance(empty_cells, int) or not (0 <= empty_cells <= 61):
        raise ValueError("empty_cells must be an integer in [0, 61]")
    rng = random.Random(seed)
    state = GameState()
    while len(state.board.empty_cells()) > empty_cells:
        vacancies = state.board.empty_cells()
        take = min(state.stones_allowed_this_turn(), len(vacancies) - empty_cells)
        state.apply_turn(rng.sample(vacancies, take))
    return state


def fingerprint(state: GameState) -> Tuple:
    """Detect unexpected changes to a shared game position after search."""
    return (
        tuple(state.board.cells.items()),
        tuple(sorted(state.scores.items())),
        state.to_move,
        state.score_increased_last_turn,
        state.is_opening_move,
        tuple(
            (e.player, tuple(e.cells), tuple(sorted(e.scores_before.items())),
             e.opponent_score_increased_before)
            for e in state.history
        ),
    )
