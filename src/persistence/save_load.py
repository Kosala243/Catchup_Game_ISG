"""Save/restore Catchup games with atomic writes and history verification."""

import json
import os
import tempfile
from typing import Any, Dict

from ..game.state import GameState


def _state_to_dict(state: GameState) -> Dict[str, Any]:
    return {
        "cells": [[list(cell), colour] for cell, colour in state.board.cells.items()],
        "scores": dict(state.scores),
        "to_move": state.to_move,
        "score_increased_last_turn": state.score_increased_last_turn,
        "is_opening_move": state.is_opening_move,
        "history": [
            {
                "player": entry.player,
                "cells": [list(cell) for cell in entry.cells],
                "scores_before": dict(entry.scores_before),
                "opponent_score_increased_before": entry.opponent_score_increased_before,
            }
            for entry in state.history
        ],
    }


def _state_from_dict(data: Dict[str, Any]) -> GameState:
    """Replay saved moves so board, scores, bonus flag and history agree."""
    if not isinstance(data, dict) or not isinstance(data.get("history"), list):
        raise ValueError("invalid Catchup save structure")

    state = GameState()
    try:
        for entry in data["history"]:
            chosen = [tuple(cell) for cell in entry["cells"]]
            state.apply_turn(chosen)
    except (TypeError, KeyError, ValueError, IndexError) as error:
        raise ValueError("invalid move history in Catchup save") from error

    if _state_to_dict(state) != data:
        raise ValueError("saved position is inconsistent with its move history")
    return state


def save_game(state: GameState, path: str) -> None:
    """Replace the existing save only after the new JSON file is complete."""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=directory,
            prefix=".catchup_", suffix=".tmp", delete=False,
        ) as temporary:
            temp_path = temporary.name
            json.dump(_state_to_dict(state), temporary)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path is not None and os.path.exists(temp_path):
            os.remove(temp_path)


def load_game(path: str) -> GameState:
    with open(path, "r", encoding="utf-8") as handle:
        return _state_from_dict(json.load(handle))