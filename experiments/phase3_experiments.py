"""Reproducible Phase 3 comparisons. Run: python -m experiments.phase3_benchmark

The script benchmarks fixed positions and reports time + search metrics. It does
not claim that a faster search automatically produces a stronger playing engine.
"""
import csv
import math
import os
import random
import time

from src.engine.search import SearchStats, alpha_beta
from src.game.state import GameState


CONFIGURATIONS = (
    ("baseline", False, False),
    ("tt_only", True, False),
    ("ordering_only", False, True),
    ("tt_and_ordering", True, True),
)
POSITIONS = ((33, 35, 3), (34, 19, 3), (35, 7, 4))  # (seed, empty cells, depth)
OUTFILE = "experiments/results/phase3_benchmark.csv"


def position(seed: int, empties_left: int) -> GameState:
    rng = random.Random(seed)
    state = GameState()
    while len(state.board.empty_cells()) > empties_left:
        vacancies = state.board.empty_cells()
        count = min(state.stones_allowed_this_turn(), len(vacancies) - empties_left)
        state.apply_turn(rng.sample(vacancies, count))
    return state


def run(path: str = OUTFILE):
    rows = []
    for seed, empties, depth in POSITIONS:
        state = position(seed, empties)
        for label, use_tt, use_ordering in CONFIGURATIONS:
            stats = SearchStats()
            started = time.monotonic()
            value, move = alpha_beta(
                state, depth, -math.inf, math.inf, state.to_move,
                max_branch=12, max_cells=14,
                use_tt=use_tt, use_ordering=use_ordering, stats=stats,
            )
            elapsed = time.monotonic() - started
            record = {
                "seed": seed,
                "empty_cells": empties,
                "depth": depth,
                "configuration": label,
                "value": value,
                "move": " ".join(str(cell) for cell in move),
                "elapsed_seconds": round(elapsed, 6),
                "nodes": stats.nodes,
                "cutoffs": stats.cutoffs,
                "tt_hits": stats.tt_hits,
                "tt_cutoffs": stats.tt_cutoffs,
                "tt_stores": stats.tt_stores,
            }
            rows.append(record)
            print(
                f"seed={seed} empty={empties} depth={depth} {label:17s} "
                f"time={elapsed:.3f}s nodes={stats.nodes:5d} "
                f"tt_hits={stats.tt_hits:4d} value={value:.2f}"
            )
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved results: {path}")
    return rows


if __name__ == "__main__":
    run()