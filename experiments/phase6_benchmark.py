"""Phase 6 search benchmark: identical positions and search depths.

Run: python -m experiments.phase6_benchmark --depth 3 --repeats 2
Outputs experiments/results/phase6_benchmark.csv by default.

Benchmark timings are CPU/machine dependent. These experiments do not
establish playing strength; use phase6_matchups for head-to-head games.
"""
import argparse
import csv
from datetime import datetime, timezone
import math
from pathlib import Path
import time

from src.engine.search import SearchStats, alpha_beta
from src.game.notation import format_turn
from experiments.phase6_common import CONFIGS, build_position, fingerprint

DEFAULT_POSITIONS = ((31, 37), (32, 21), (33, 8))
FIELDS = (
    "timestamp_utc", "seed", "empty_cells", "depth", "repeat", "configuration",
    "use_tt", "use_ordering", "max_branch", "max_cells", "to_move",
    "value", "best_move", "elapsed_seconds", "nodes", "leaves", "cutoffs",
    "searched_moves", "generated_moves", "tt_hits", "tt_cutoffs", "tt_stores",
    "nodes_per_second", "same_value_as_baseline",
)


def benchmark(depth=3, repeats=1, max_branch=12, max_cells=14,
              positions=DEFAULT_POSITIONS, output="experiments/results/phase6_benchmark.csv"):
    if depth < 1 or repeats < 1 or max_branch < 1 or max_cells < 1:
        raise ValueError("depth, repeats, max_branch, and max_cells must be positive")
    results = []
    for seed, empties in positions:
        state = build_position(seed, empties)
        if state.is_game_over():
            raise ValueError("Benchmark requires a nonterminal position")
        original = fingerprint(state)
        for repeat in range(1, repeats + 1):
            reference = None
            for config in CONFIGS:
                stats = SearchStats()
                started = time.perf_counter()
                value, move = alpha_beta(
                    state, depth, -math.inf, math.inf, state.to_move,
                    max_branch=max_branch, max_cells=max_cells, stats=stats,
                    use_tt=config.use_tt, use_ordering=config.use_ordering,
                )
                duration = time.perf_counter() - started
                if fingerprint(state) != original:
                    raise AssertionError(f"Search mutated position for {config.name}")
                if move is None or len(move) > state.stones_allowed_this_turn():
                    raise AssertionError(f"Search returned invalid move for {config.name}")
                if reference is None:
                    reference = value
                agreement = math.isclose(value, reference, abs_tol=1e-7, rel_tol=1e-9)
                row = {
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "seed": seed, "empty_cells": empties, "depth": depth,
                    "repeat": repeat, "configuration": config.name,
                    "use_tt": int(config.use_tt), "use_ordering": int(config.use_ordering),
                    "max_branch": max_branch, "max_cells": max_cells,
                    "to_move": state.to_move, "value": value,
                    "best_move": format_turn(move),
                    "elapsed_seconds": round(duration, 8), "nodes": stats.nodes,
                    "leaves": stats.leaves, "cutoffs": stats.cutoffs,
                    "searched_moves": stats.searched_moves,
                    "generated_moves": stats.generated_moves,
                    "tt_hits": stats.tt_hits, "tt_cutoffs": stats.tt_cutoffs,
                    "tt_stores": stats.tt_stores,
                    "nodes_per_second": round(stats.nodes / duration, 2) if duration else 0,
                    "same_value_as_baseline": int(agreement),
                }
                results.append(row)
                print(f"seed={seed} empty={empties:2d} repeat={repeat} {config.name:17s} "
                      f"{duration:.3f}s nodes={stats.nodes:5d} depth={depth} "
                      f"value={value:.2f}{'' if agreement else ' VALUE MISMATCH'}")
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(results)
    print(f"Saved {len(results)} benchmark rows to {path}")
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--depth", type=int, default=3)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--max-branch", type=int, default=12)
    parser.add_argument("--max-cells", type=int, default=14)
    parser.add_argument("--output", default="experiments/results/phase6_benchmark.csv")
    args = parser.parse_args()
    benchmark(args.depth, args.repeats, args.max_branch, args.max_cells, output=args.output)


if __name__ == "__main__":
    main()
