"""Colour-swapped, reproducible complete games between search configurations.

Default A='baseline' versus B='tt_and_ordering'. Both use the SAME
candidate generator, evaluator, depth and per-player clock allocation.
Each seed supplies ONE fixed White opening for both colour-swapped games.
A paired comparison is two games, not a claim of statistical significance.

Example:
python -m experiments.phase6_matchups --pairs 2 --budget-seconds 5 --max-depth 3
"""
import argparse
import csv
import math
from pathlib import Path
import random
import time

from src.board.board import WHITE, BLACK, other
from src.engine.search import SearchStats, iterative_deepening
from src.engine.time_manager import Clock, allocate_time
from src.game.notation import format_turn
from src.game.state import GameState
from experiments.phase6_common import find_config, fingerprint

GAME_FIELDS = (
    "pair", "seed", "game", "opening", "white_config", "black_config", "winner",
    "winner_config", "termination", "turns", "white_score", "black_score",
    "white_time_used", "black_time_used", "white_time_left", "black_time_left",
    "white_nodes", "black_nodes", "white_completed_depth_max", "black_completed_depth_max",
)
MOVE_FIELDS = (
    "pair", "game", "ply", "side", "configuration", "move", "stones",
    "empty_before", "allowed", "white_score", "black_score", "budget_seconds",
    "elapsed_seconds", "clock_left", "completed_depth", "nodes", "leaves",
    "cutoffs", "tt_hits", "tt_cutoffs", "tt_stores", "timed_out_iteration",
)


def play_game(pair, game, seed, opening, white_config, black_config,
              budget_seconds, max_depth, max_branch=12, max_cells=14):
    state = GameState()
    state.apply_turn([opening])   # same White opening for both games; not charged
    clocks = {WHITE: Clock(budget_seconds), BLACK: Clock(budget_seconds)}
    configs = {WHITE: white_config, BLACK: black_config}
    total_nodes = {WHITE: 0, BLACK: 0}
    deepest = {WHITE: 0, BLACK: 0}
    log = []
    forfeit = None
    game_id = f"{pair}-{game}"
    while not state.is_game_over():
        side = state.to_move
        remaining = clocks[side].time_left()
        if remaining <= 0:
            forfeit = f"{side} clock exhausted"
            break
        vacancies = state.board.empty_cells()
        allowed = state.stones_allowed_this_turn()
        estimated_turns = max(1, math.ceil(len(vacancies) / 3))
        allowance = allocate_time(remaining, estimated_turns)
        config = configs[side]
        stats = SearchStats()
        before = fingerprint(state)
        clocks[side].start_move()
        started = time.perf_counter()
        try:
            turn = iterative_deepening(
                state, allowance, side, max_depth=max_depth,
                max_branch=max_branch, max_cells=max_cells,
                stats=stats, use_tt=config.use_tt,
                use_ordering=config.use_ordering,
            )
        except Exception as error:
            forfeit = f"{side} search error ({type(error).__name__}: {error})"
            turn = None
        finally:
            elapsed = time.perf_counter() - started
            clocks[side].stop_move()
        if forfeit is not None:
            break
        if fingerprint(state) != before:
            forfeit = f"{side} search modified shared state"
            break
        if clocks[side].time_left() <= 0:
            forfeit = f"{side} clock exhausted"
            break
        try:
            # GameState independently validates legality and full-turn rules.
            state.apply_turn(turn)
        except (ValueError, TypeError) as error:
            forfeit = f"{side} illegal action ({error})"
            break
        total_nodes[side] += stats.nodes
        deepest[side] = max(deepest[side], stats.completed_depth)
        log.append({
            "pair": pair, "game": game_id, "ply": len(state.history), "side": side,
            "configuration": config.name, "move": format_turn(turn),
            "stones": len(turn), "empty_before": len(vacancies), "allowed": allowed,
            "white_score": state.scores[WHITE], "black_score": state.scores[BLACK],
            "budget_seconds": round(allowance, 6), "elapsed_seconds": round(elapsed, 6),
            "clock_left": round(clocks[side].time_left(), 6),
            "completed_depth": stats.completed_depth,
            "nodes": stats.nodes, "leaves": stats.leaves, "cutoffs": stats.cutoffs,
            "tt_hits": stats.tt_hits, "tt_cutoffs": stats.tt_cutoffs,
            "tt_stores": stats.tt_stores, "timed_out_iteration": int(stats.timed_out),
        })
    if forfeit:
        forfeiting_side = state.to_move
        winner = other(forfeiting_side)
        termination = forfeit
    else:
        winner = state.winner()
        termination = "board_full"
    row = {
        "pair": pair, "seed": seed, "game": game_id,
        "opening": format_turn([opening]),
        "white_config": white_config.name, "black_config": black_config.name,
        "winner": winner if winner is not None else "draw",
        "winner_config": configs[winner].name if winner is not None else "draw",
        "termination": termination, "turns": len(state.history),
        "white_score": state.scores[WHITE], "black_score": state.scores[BLACK],
        "white_time_used": round(budget_seconds - clocks[WHITE].time_left(), 6),
        "black_time_used": round(budget_seconds - clocks[BLACK].time_left(), 6),
        "white_time_left": round(clocks[WHITE].time_left(), 6),
        "black_time_left": round(clocks[BLACK].time_left(), 6),
        "white_nodes": total_nodes[WHITE], "black_nodes": total_nodes[BLACK],
        "white_completed_depth_max": deepest[WHITE],
        "black_completed_depth_max": deepest[BLACK],
    }
    return row, log


def run(pairs=2, budget_seconds=10.0, max_depth=4, max_branch=12,
        max_cells=14, seed_start=2026, a="baseline", b="tt_and_ordering",
        output_dir="experiments/results"):
    if pairs < 1 or not (0 < budget_seconds <= 600):
        raise ValueError("pairs >= 1 and 0 < budget_seconds <= 600 required")
    if min(max_depth, max_branch, max_cells) < 1 or a == b:
        raise ValueError("positive search parameters and distinct configurations required")
    first, second = find_config(a), find_config(b)
    games, moves = [], []
    for pair in range(1, pairs + 1):
        seed = seed_start + pair - 1
        opening = random.Random(seed).choice(GameState().board.empty_cells())
        for game, (white, black) in enumerate(((first, second), (second, first)), 1):
            result, detail = play_game(
                pair, game, seed, opening, white, black, budget_seconds,
                max_depth, max_branch, max_cells,
            )
            games.append(result)
            moves.extend(detail)
            print(f"pair={pair} game={game} W={white.name} B={black.name} "
                  f"winner={result['winner_config']} result={result['termination']} "
                  f"turns={result['turns']}")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    for name, columns, rows in (("phase6_games.csv", GAME_FIELDS, games),
                                ("phase6_moves.csv", MOVE_FIELDS, moves)):
        with (output / name).open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)
    print(f"Saved {len(games)} games, {len(moves)} searched moves in {output}")
    return games, moves


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pairs", type=int, default=2)
    p.add_argument("--budget-seconds", type=float, default=10.0)
    p.add_argument("--max-depth", type=int, default=4)
    p.add_argument("--max-branch", type=int, default=12)
    p.add_argument("--max-cells", type=int, default=14)
    p.add_argument("--seed-start", type=int, default=2026)
    p.add_argument("--a", choices=["baseline", "tt_only", "ordering_only", "tt_and_ordering"], default="baseline")
    p.add_argument("--b", choices=["baseline", "tt_only", "ordering_only", "tt_and_ordering"], default="tt_and_ordering")
    p.add_argument("--output-dir", default="experiments/results")
    args = p.parse_args()
    run(**vars(args))


if __name__ == "__main__":
    main()
