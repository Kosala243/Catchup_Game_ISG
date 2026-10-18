"""Atomic Catchup save/load with verified game history and optional AI clock.

save_game/load_game preserve the original Phase 1 plain-game format.
save_tournament_session/load_tournament_session store an additional clock and
AI colour so --resume cannot silently give the AI a fresh 600 seconds.
"""
import json
import math
import os
import tempfile
from typing import Any, Dict, Tuple

from ..board.board import WHITE, BLACK
from ..engine.time_manager import Clock
from ..game.state import GameState

SESSION_FORMAT = "catchup-tournament-v1"


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


def _atomic_save(data: Dict[str, Any], path: str) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=directory,
            prefix=".catchup_", suffix=".tmp", delete=False,
        ) as temporary:
            temp_path = temporary.name
            json.dump(data, temporary)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path is not None and os.path.exists(temp_path):
            os.remove(temp_path)


def _read_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def save_game(state: GameState, path: str) -> None:
    """Save a plain GameState in the original Phase 1 format."""
    _atomic_save(_state_to_dict(state), path)


def load_game(path: str) -> GameState:
    """Read plain game saves or the game part of a tournament session."""
    data = _read_json(path)
    if isinstance(data, dict) and data.get("format") == SESSION_FORMAT:
        return _state_from_dict(data["game"])
    return _state_from_dict(data)


def _valid_clock_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise ValueError(f"{label} must be numeric")
    n = float(value)
    if not math.isfinite(n) or n < 0:
        raise ValueError(f"{label} must be finite and nonnegative")
    return n


def save_tournament_session(
    state: GameState, path: str, ai_colour: str, clock: Clock,
    reserved_seconds: float = 0.0,
) -> None:
    """Save the board and clock atomically.

    `reserved_seconds` is used immediately before an AI search starts. On a
    crash during search, loading conservatively charges that budget once.
    Successful searches replace the reservation with actual consumed time.
    """
    if ai_colour not in (WHITE, BLACK):
        raise ValueError("invalid AI colour")
    if clock.is_running:
        raise RuntimeError("cannot checkpoint the clock while it is running")
    reserved = _valid_clock_number(reserved_seconds, "reserved_seconds")
    remaining = clock.time_left()
    if reserved > remaining:
        raise ValueError("reserved_seconds exceeds the remaining clock")
    _atomic_save({
        "format": SESSION_FORMAT,
        "game": _state_to_dict(state),
        "ai_colour": ai_colour,
        "clock": {
            "total_seconds": clock.total_seconds,
            "remaining_seconds": remaining,
            "reserved_seconds": reserved,
        },
    }, path)


def load_tournament_session(
    path: str, expected_colour: str, max_total_seconds: float = 600.0,
) -> Tuple[GameState, Clock]:
    """Restore a saved game with no time reset and correct colour matching."""
    data = _read_json(path)
    if not isinstance(data, dict) or data.get("format") != SESSION_FORMAT:
        raise ValueError(
            "This save has no tournament clock information; it cannot safely "
            "be resumed with a fresh time allowance."
        )
    if expected_colour not in (WHITE, BLACK) or data.get("ai_colour") != expected_colour:
        raise ValueError("saved AI colour does not match --colour")
    try:
        payload = data["clock"]
        total = _valid_clock_number(payload["total_seconds"], "total_seconds")
        remaining = _valid_clock_number(payload["remaining_seconds"], "remaining_seconds")
        reserved = _valid_clock_number(payload["reserved_seconds"], "reserved_seconds")
    except (KeyError, TypeError) as error:
        raise ValueError("invalid tournament clock metadata") from error
    if total <= 0 or total > max_total_seconds or remaining > total or reserved > remaining:
        raise ValueError("saved tournament clock exceeds permitted time")
    state = _state_from_dict(data["game"])
    clock = Clock(total_seconds=total, remaining_seconds=remaining - reserved)
    return state, clock
