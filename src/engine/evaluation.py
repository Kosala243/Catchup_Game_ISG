"""Catchup heuristic for nonterminal search nodes.

Largest connected group remains the most important feature, but potential
one-cell mergers and opponent threats also matter. Terminal outcomes ALWAYS
use the official lexicographic group comparison, not this heuristic.
"""
from ..board.board import BLACK, WHITE, other
from ..board.coordinates import neighbours
from ..game.state import GameState
from .move_generation import _component_map

WIN_VALUE = 1_000_000.0


def _features_from_maps(state: GameState, colour: str, mapping: dict, sizes: list, enemy_map: dict) -> dict:
    board = state.board
    frontier = set()
    best_growth = 0
    bridges = 0
    threatened_connections = 0
    opposing = other(colour)
    for stone in board.stones_of(colour):
        frontier.update(n for n in neighbours(stone) if board.cells[n] is None)
    largest = max(sizes, default=0)
    for cell in frontier:
        own = {mapping[n] for n in neighbours(cell) if n in mapping}
        joined = 1 + sum(sizes[k] for k in own)
        best_growth = max(best_growth, joined - largest)
        if len(own) >= 2:
            bridges += 1
        # A potential connection cell may be occupied by the enemy first.
        if any(n in enemy_map for n in neighbours(cell)):
            threatened_connections += 1
    return {
        "largest": largest,
        "second": sorted(sizes, reverse=True)[1] if len(sizes) > 1 else 0,
        "stones": sum(sizes),
        "frontier": len(frontier),
        "best_growth": min(10, best_growth),
        "bridge_cells": bridges,
        "contested_frontier": threatened_connections,
    }


def position_features(state: GameState, colour: str) -> dict:
    """Human-readable components for debugging and comparisons."""
    mapping, sizes = _component_map(state, colour)
    enemy_map, _ = _component_map(state, other(colour))
    return _features_from_maps(state, colour, mapping, sizes, enemy_map)


def _weighted_features(state: GameState, p: dict) -> float:
    progress = (61 - len(state.board.empty_cells())) / 61.0
    return (
        (12.0 + 7.0 * progress) * p["largest"]
        + (3.5 + 1.0 * progress) * p["second"]
        + 0.5 * p["stones"]
        + 0.30 * p["frontier"]
        + 1.8 * p["best_growth"]
        + 1.2 * min(p["bridge_cells"], 6)
        + 0.25 * p["contested_frontier"]
    )


def _position_features(state: GameState, colour: str) -> float:
    return _weighted_features(state, position_features(state, colour))


def evaluate(state: GameState, colour: str) -> float:
    if colour not in (WHITE, BLACK):
        raise ValueError(f"invalid colour: {colour!r}")
    opponent = other(colour)
    if state.is_game_over():
        winner = state.winner()
        return 0.0 if winner is None else (WIN_VALUE if winner == colour else -WIN_VALUE)
    own_map, own_sizes = _component_map(state, colour)
    foe_map, foe_sizes = _component_map(state, opponent)
    own = _features_from_maps(state, colour, own_map, own_sizes, foe_map)
    foe = _features_from_maps(state, opponent, foe_map, foe_sizes, own_map)
    value = _weighted_features(state, own) - _weighted_features(state, foe)
    # The active player can place 3 only if the *last* score increase enabled
    # it. Reward the side with the opportunity, not the one that granted it.
    if state.stones_allowed_this_turn() == 3:
        value += 6.5 if state.to_move == colour else -6.5
    return value


def describe_evaluation(state: GameState, colour: str) -> dict:
    """Read-only diagnostic; evaluate() remains the canonical search score."""
    if colour not in (WHITE, BLACK):
        raise ValueError(f"invalid colour: {colour!r}")
    return {"perspective": colour, "own": position_features(state, colour),
            "opponent": position_features(state, other(colour)),
            "score": evaluate(state, colour)}
