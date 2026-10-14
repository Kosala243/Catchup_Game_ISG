"""
JSON save/restore for GameState - the crash-recovery feature required by the
tournament rules ("restart a game from the last position").
"""

import json
import os
from typing import Any, Dict

from ..game.state import GameState, HistoryEntry


def _state_to_dict(state: GameState) -> Dict[str, Any]:
    return {
        "cells": [[list(cell), colour] for cell, colour in state.board.cells.items()],
        "scores": state.scores,
        "to_move": state.to_move,
        "score_increased_last_turn": state.score_increased_last_turn,
        "is_opening_move": state.is_opening_move,
        "history": [
            {
                "player": e.player,
                "cells": [list(c) for c in e.cells],
                "scores_before": e.scores_before,
                "opponent_score_increased_before": e.opponent_score_increased_before,
            }
            for e in state.history
        ],
    }


def _state_from_dict(data: Dict[str, Any]) -> GameState:
    state = GameState()
    for cell, colour in data["cells"]:
        state.board.cells[tuple(cell)] = colour
    state.scores = data["scores"]
    state.to_move = data["to_move"]
    state.score_increased_last_turn = data["score_increased_last_turn"]
    state.is_opening_move = data["is_opening_move"]
    state.history = [
        HistoryEntry(
            player=e["player"],
            cells=[tuple(c) for c in e["cells"]],
            scores_before=e["scores_before"],
            opponent_score_increased_before=e["opponent_score_increased_before"],
        )
        for e in data["history"]
    ]
    return state


def save_game(state: GameState, path: str) -> None:
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_state_to_dict(state), f)


def load_game(path: str) -> GameState:
    with open(path, "r", encoding="utf-8") as f:
        return _state_from_dict(json.load(f))
