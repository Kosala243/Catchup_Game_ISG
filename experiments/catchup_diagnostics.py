"""Read-only, reproducible inspection of the existing Catchup alpha-beta engine.

This development utility REUSES alpha_beta, MoveOrdering, TranspositionTable,
and Phase 6's seeded legal positions. It does not alter game-playing logic.
An iteration here is one completed iterative-deepening DEPTH (one complete
Catchup turn per ply), not a stone placement or individual node expansion.
"""
from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from threading import Event
import time
from typing import Callable, Optional

from experiments.phase6_common import build_position, fingerprint
from src.board.board import BLACK, WHITE
from src.engine.move_generation import SearchTimeout
from src.engine.move_ordering import MoveOrdering
from src.engine.search import SearchStats, alpha_beta
from src.engine.transposition_table import TranspositionTable, position_key
from src.game.notation import format_turn


@dataclass(frozen=True)
class Experiment:
    number: int
    title: str
    use_tt: bool
    use_ordering: bool
    configuration: str


# Exactly the configurations used by the existing Phase 6 comparisons.
EXPERIMENTS = (
    Experiment(1, "Baseline", False, False, "baseline"),
    Experiment(2, "Move ordering", False, True, "ordering_only"),
    Experiment(3, "Transposition table", True, False, "tt_only"),
    Experiment(4, "TT + ordering", True, True, "tt_and_ordering"),
)


def get_experiment(number: int) -> Experiment:
    for experiment in EXPERIMENTS:
        if experiment.number == number:
            return experiment
    raise ValueError("experiment must be an integer from 1 to 4")


def _tt_sample(table: Optional[TranspositionTable], limit: int) -> tuple[list[dict], dict]:
    """Bounded VIEW of actual entries, not a fabricated log of every lookup.

    This intentionally uses the table's current private storage for
    inspection. If the engine changes its table internals, update this
    diagnostic adapter rather than the search algorithm.
    """
    if table is None:
        return [], {"size": 0, "exact": 0, "lower": 0, "upper": 0, "capacity": 0}
    entries = list(table._entries.items())
    counts = {"size": len(entries), "exact": 0, "lower": 0, "upper": 0,
              "capacity": table.max_entries}
    for _, entry in entries:
        counts[entry.bound.value] += 1
    # Show deepest first; break ties by descending quality (EXACT before bounds),
    # then existing FIFO insertion order. Never return more than `limit` items.
    ranked = sorted(enumerate(entries), key=lambda item: (
        -item[1][1].depth, item[1][1].bound.value != "exact", item[0]
    )) if limit else []
    sample = []
    for _, (key, entry) in ranked[:limit]:
        white_mask, black_mask, mover, bonus, opening, white_score, black_score, perspective, branch, cells, full = key[:11]
        sample.append({
            "depth": entry.depth, "bound": entry.bound.value,
            "value": entry.value,
            "best_turn": format_turn(list(entry.best_move)) if entry.best_move else "—",
            "to_move": mover, "bonus_previous_turn": bool(bonus),
            "opening_move": bool(opening),
            "white_score": white_score, "black_score": black_score,
            "white_stones": white_mask.bit_count(), "black_stones": black_mask.bit_count(),
            "white_mask": f"0x{white_mask:016x}", "black_mask": f"0x{black_mask:016x}",
            "perspective": perspective, "max_branch": branch,
            "max_cells": cells, "full_width": full,
        })
    return sample, counts


def run_experiment(
    number: int, *, seed: int = 33, empty_cells: int = 19,
    max_depth: int = 4, budget_seconds: float = 4.0,
    max_branch: int = 12, max_cells: int = 14,
    output_dir: str | Path = "experiments/results",
    on_event: Optional[Callable[[dict], None]] = None,
    cancel: Optional[Event] = None,
    tt_preview_limit: int = 25,
) -> dict:
    """Search one reproducible position while reporting completed depth iterations.

    A SINGLE shared time budget covers all search depths in this experiment.
    Iterations share the same TT and move-ordering information, like the
    engine's iterative_deepening(), but its internals are not modified.
    Reported node counts are per iteration; TT size is cumulative.
    """
    exp = get_experiment(number)
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be an integer")
    if isinstance(empty_cells, bool) or not isinstance(empty_cells, int) or not 1 <= empty_cells <= 60:
        raise ValueError("empty_cells must be from 1 to 60")
    if any(isinstance(x, bool) or not isinstance(x, int) or x < 1
           for x in (max_depth, max_branch, max_cells)):
        raise ValueError("max_depth, max_branch and max_cells must be positive integers")
    if not isinstance(tt_preview_limit, int) or not (0 <= tt_preview_limit <= 100):
        raise ValueError("tt_preview_limit must be between 0 and 100")
    if isinstance(budget_seconds, bool) or not isinstance(budget_seconds, (float, int)) \
            or not math.isfinite(budget_seconds) or budget_seconds < 0 or budget_seconds > 600:
        raise ValueError("budget_seconds must be finite and between 0 and 600")

    position = build_position(seed, empty_cells)
    if position.is_game_over():
        raise ValueError("experiment position must not be terminal")
    original = fingerprint(position)
    perspective = position.to_move
    table = TranspositionTable() if exp.use_tt else None
    ordering = MoveOrdering() if exp.use_ordering else None
    initial_key = position_key(position, perspective, max_branch, max_cells, False)
    iterations = []
    fallback = [position.board.empty_cells()[0]]
    best = fallback
    best_value = None
    completed_depth = 0
    timed_out = False
    cancelled = False
    started = time.monotonic()
    deadline = started + float(budget_seconds)

    def emit(message: dict) -> None:
        if on_event is not None:
            on_event(message)

    emit({"kind": "started", "number": exp.number, "configuration": exp.configuration,
          "to_move": perspective, "seed": seed, "empty_cells": empty_cells})

    for depth in range(1, max_depth + 1):
        if cancel is not None and cancel.is_set():
            cancelled = True
            break
        if time.monotonic() >= deadline:
            timed_out = True
            break
        stats = SearchStats()
        iteration_start = time.monotonic()
        try:
            value, action = alpha_beta(
                position, depth, -math.inf, math.inf, perspective,
                max_branch=max_branch, max_cells=max_cells,
                deadline=deadline, stats=stats, table=table, ordering=ordering,
                use_tt=exp.use_tt, use_ordering=exp.use_ordering,
            )
        except SearchTimeout:
            timed_out = True
            emit({"kind": "interrupted", "depth": depth,
                  "elapsed_seconds": round(time.monotonic() - iteration_start, 6)})
            break
        if fingerprint(position) != original:
            raise AssertionError("Search changed its input state")
        if action is None:
            raise AssertionError("Nonterminal alpha_beta returned no turn")
        # Validate the action on a copy. A legal whole turn may contain 1-3 cells.
        trial = position.copy()
        trial.apply_turn(action)
        completed_depth = depth
        stats.completed_depth = depth
        best, best_value = action, value
        sample, counts = _tt_sample(table, 0)
        record = {
            "depth": depth, "evaluation": float(value),
            "best_turn": format_turn(action),
            "stones": len(action), "elapsed_seconds": round(time.monotonic() - iteration_start, 6),
            "tt_size": counts["size"], **asdict(stats),
        }
        iterations.append(record)
        emit({"kind": "iteration", "row": record})

    if fingerprint(position) != original:
        raise AssertionError("Search did not restore the board/history")
    sample, counts = _tt_sample(table, tt_preview_limit)
    elapsed = time.monotonic() - started
    report = {
        "record_type": "catchup-search-diagnostics-v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "experiment": asdict(exp),
        "position": {
            "seed": seed, "empty_cells": empty_cells, "to_move": perspective,
            "white_score": position.scores[WHITE], "black_score": position.scores[BLACK],
            "previous_turn_increased_score": position.score_increased_last_turn,
            "opening_move": position.is_opening_move, "history_length": len(position.history),
        },
        "parameters": {"max_depth": max_depth, "budget_seconds": float(budget_seconds),
                       "max_branch": max_branch, "max_cells": max_cells,
                       "tt_preview_limit": tt_preview_limit},
        "result": {
            "best_turn": format_turn(best), "evaluation": best_value,
            "completed_depth": completed_depth, "timed_out": timed_out,
            "cancelled": cancelled, "elapsed_seconds": round(elapsed, 6),
            "fallback_used": completed_depth == 0,
        },
        "iterations": iterations, "tt_summary": counts, "tt_preview": sample,
        "root_key": {"white_mask": f"0x{initial_key[0]:016x}",
                     "black_mask": f"0x{initial_key[1]:016x}"},
    }

    # Save an individual report and an iteration CSV with uniquely named files
    # to avoid accidentally overwriting earlier experiment measurements.
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    filename = f"catchup_exp{number}_{seed}_{empty_cells}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
    report_path = output / (filename + ".json")
    csv_path = output / (filename + "_iterations.csv")
    report_path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    if iterations:
        with csv_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(iterations[0]))
            writer.writeheader()
            writer.writerows(iterations)
    report["saved_json"] = str(report_path)
    report["saved_csv"] = str(csv_path) if iterations else None
    emit({"kind": "complete", "report": report})
    return report


def main() -> None:
    """Optional console version; graphical controls are in catchup_dashboard."""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=int, choices=range(1, 5), required=True)
    parser.add_argument("--seed", type=int, default=33)
    parser.add_argument("--empty-cells", type=int, default=19)
    parser.add_argument("--max-depth", type=int, default=4)
    parser.add_argument("--budget-seconds", type=float, default=4.0)
    args = parser.parse_args()

    def log(event):
        if event["kind"] == "iteration":
            row = event["row"]
            print(f"Depth={row['depth']} | Turn={row['best_turn']} | "
                  f"Eval={row['evaluation']:+.2f} | "
                  f"Nodes={row['nodes']} | Cutoffs={row['cutoffs']} | "
                  f"TT Hits={row['tt_hits']} | TT Size={row['tt_size']} | "
                  f"Time={row['elapsed_seconds']:.3f}s")

    report = run_experiment(args.experiment, seed=args.seed,
                            empty_cells=args.empty_cells,
                            max_depth=args.max_depth,
                            budget_seconds=args.budget_seconds, on_event=log)
    print("Final:", report["result"])
    print("TT summary:", report["tt_summary"])
    print("JSON:", report["saved_json"])
    print("CSV:", report["saved_csv"])


if __name__ == "__main__":
    main()
