"""Catchup experimental lab: reproducible search traces, benchmarks, paired games, and reports.

Use ``python -m experiments.lab --help`` to see commands.
All games use the existing Catchup engine and rules; this is measurement code only.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import time
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from threading import Event
from typing import Callable, Optional, Tuple

from src.board.board import BLACK, WHITE, other
from src.engine.move_generation import SearchTimeout
from src.engine.move_ordering import MoveOrdering
from src.engine.search import SearchStats, alpha_beta, iterative_deepening
from src.engine.time_manager import Clock, allocate_time
from src.engine.transposition_table import TranspositionTable, position_key
from src.game.notation import format_turn
from src.game.state import GameState

# --- Reproducible, legal game positions and experiment configurations ---

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



# --- Iterative-deepening trace and bounded TT inspection ---

@dataclass(frozen=True)
class Experiment:
    number: int
    title: str
    use_tt: bool
    use_ordering: bool
    configuration: str


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



# --- Controlled node-count and elapsed-time benchmarks ---

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



# --- Colour-swapped algorithm-configuration matches ---

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


def run_matchups(pairs=2, budget_seconds=10.0, max_depth=4, max_branch=12,
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



# --- Colour-swapped depth/endgame/caching strength matches ---

@dataclass(frozen=True)
class Profile:
    name: str
    depth: int
    endgame_cells: int
    persistent_tt: bool


CONTROL = Profile('control_depth4', 4, 0, False)


ENHANCED = Profile('enhanced_depth6', 6, 7, True)


def one_game(seed, white: Profile, black: Profile, seconds: float, max_branch=12, max_cells=14):
    state = GameState()
    # Identical fixed White opening for both swapped games; do not charge it
    # to either profile. All later AI decisions are timed.
    state.apply_turn([random.Random(seed).choice(state.board.empty_cells())])
    profiles = {WHITE: white, BLACK: black}
    clocks = {c: Clock(seconds) for c in (WHITE, BLACK)}
    tables = {c: TranspositionTable() for c in (WHITE, BLACK)}
    ordering = {c: MoveOrdering() for c in (WHITE, BLACK)}
    errors = []
    nodes = {WHITE: 0, BLACK: 0}
    depths = {WHITE: [], BLACK: []}
    while not state.is_game_over():
        colour = state.to_move
        left = clocks[colour].time_left()
        if left <= 0:
            errors.append(f'{colour}: time exhausted')
            break
        p = profiles[colour]
        budget = allocate_time(left, max(1, math.ceil(len(state.board.empty_cells()) / 3)))
        stats = SearchStats()
        clocks[colour].start_move()
        try:
            chosen = iterative_deepening(
                state, budget, colour, max_depth=p.depth,
                max_branch=max_branch, max_cells=max_cells,
                endgame_full_width_cells=p.endgame_cells,
                table=tables[colour] if p.persistent_tt else None,
                ordering=ordering[colour] if p.persistent_tt else None,
                stats=stats,
            )
        except Exception as error:
            errors.append(f'{colour}: {type(error).__name__} {error}')
            break
        finally:
            clocks[colour].stop_move()
        if clocks[colour].time_left() <= 0:
            errors.append(f'{colour}: time exhausted')
            break
        try:
            state.apply_turn(chosen)
        except (TypeError, ValueError) as error:
            errors.append(f'{colour}: illegal move {error}')
            break
        nodes[colour] += stats.nodes
        depths[colour].append(stats.completed_depth)
    winner = other(state.to_move) if errors else state.winner()
    profile_winner = profiles[winner].name if winner is not None else 'draw'
    return {
        'seed': seed, 'white_profile': white.name, 'black_profile': black.name,
        'winner': winner or 'draw', 'winner_profile': profile_winner,
        'termination': errors[0] if errors else 'board_full',
        'turns': len(state.history), 'white_score': state.scores[WHITE],
        'black_score': state.scores[BLACK],
        'white_seconds_used': round(seconds - clocks[WHITE].time_left(), 6),
        'black_seconds_used': round(seconds - clocks[BLACK].time_left(), 6),
        'white_nodes': nodes[WHITE], 'black_nodes': nodes[BLACK],
        'white_mean_completed_depth': (round(sum(depths[WHITE])/len(depths[WHITE]), 3)
                                       if depths[WHITE] else 0),
        'black_mean_completed_depth': (round(sum(depths[BLACK])/len(depths[BLACK]), 3)
                                       if depths[BLACK] else 0),
    }


def run_strength(pairs=10, seconds=10.0, seed_start=2026, output='experiments/results/strength_matchups.csv'):
    if pairs < 1 or not (0 < seconds <= 600):
        raise ValueError('pairs must be positive; seconds must be in (0,600]')
    results = []
    for i in range(pairs):
        seed = seed_start + i
        for w, b in ((CONTROL, ENHANCED), (ENHANCED, CONTROL)):
            row = one_game(seed, w, b, seconds)
            results.append(row)
            print(f"Seed {seed}: W={w.name} B={b.name}; "
                  f"winner={row['winner_profile']}; turns={row['turns']} "
                  f"({row['termination']})", flush=True)
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    print('Results:', path)
    print('Wins:', {p.name: sum(r['winner_profile'] == p.name for r in results)
                    for p in (CONTROL, ENHANCED)})
    return results



# --- Summaries of measured CSV outputs ---

def _read(path):
    source = Path(path)
    if not source.exists():
        return []
    with source.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def summarize(result_dir="experiments/results"):
    output = Path(result_dir)
    benchmarks = _read(output / "phase6_benchmark.csv")
    games = _read(output / "phase6_games.csv")
    moves = _read(output / "phase6_moves.csv")
    lines = ["Catchup Phase 6 — measured results", "================================="]
    if benchmarks:
        grouped = defaultdict(list)
        for row in benchmarks:
            grouped[row["configuration"]].append(row)
        lines.append(f"\nSearch benchmark: {len(benchmarks)} measurements")
        for config, samples in sorted(grouped.items()):
            mean_time = mean(float(r["elapsed_seconds"]) for r in samples)
            mean_nodes = mean(int(r["nodes"]) for r in samples)
            disagree = sum(r["same_value_as_baseline"] == "0" for r in samples)
            lines.append(f"  {config:18s} mean {mean_time:.4f}s; {mean_nodes:.1f} nodes; "
                         f"{disagree} evaluation disagreements")
        lines.append("  Note: times and node counts depend on the tested positions/depth/hardware.")
    else:
        lines.append("\nSearch benchmark: no CSV found")
    if games:
        configs = sorted({g["white_config"] for g in games} |
                         {g["black_config"] for g in games})
        lines.append(f"\nPaired games: {len(games)} games ({len(games) // 2} pairs)")
        for config in configs:
            won = sum(g["winner_config"] == config for g in games)
            draws = sum(g["winner_config"] == "draw" for g in games)
            defeats = sum(g["winner_config"] not in (config, "draw") for g in games)
            white = sum(g["winner_config"] == config and g["white_config"] == config for g in games)
            lines.append(f"  {config:18s} wins {won}, draws {draws}, losses {defeats}, "
                         f"wins as White {white}")
        nonstandard = [g for g in games if g["termination"] != "board_full"]
        lines.append(f"  Forfeit/error games: {len(nonstandard)}")
        if nonstandard:
            for g in nonstandard:
                lines.append(f"    game {g['game']}: {g['termination']}")
        lines.append("  Important: small paired samples are not a statistically reliable win rate.")
    else:
        lines.append("\nPaired games: no CSV found")
    if moves:
        grouped_moves = defaultdict(list)
        for m in moves:
            grouped_moves[m["configuration"]].append(m)
        lines.append(f"\nRecorded AI decisions: {len(moves)}")
        for config, rows in sorted(grouped_moves.items()):
            depth = mean(int(r["completed_depth"]) for r in rows)
            duration = mean(float(r["elapsed_seconds"]) for r in rows)
            lines.append(f"  {config:18s} avg completed depth {depth:.2f}, "
                         f"mean move time {duration:.4f}s")
    else:
        lines.append("\nAI decisions: no CSV found")
    text = "\n".join(lines) + "\n"
    output.mkdir(parents=True, exist_ok=True)
    dest = output / "phase6_summary.txt"
    dest.write_text(text, encoding="utf-8")
    print(text)
    print(f"Saved {dest}")
    return text



# --- Plots of measured CSV outputs ---

def _read_plot(path):
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _group_means(rows, value):
    values = defaultdict(list)
    for row in rows:
        values[row["configuration"]].append(float(row[value]))
    names = sorted(values)
    return names, [mean(values[name]) for name in names]


def plot(result_dir="experiments/results"):
    # Selecting the Agg backend means this works on a headless CI/server.
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    directory = Path(result_dir)
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    benchmarks = _read_plot(directory / "phase6_benchmark.csv")
    if benchmarks:
        for value, ylabel, filename in (
            ("elapsed_seconds", "Mean search time (seconds)", "phase6_search_time.png"),
            ("nodes", "Mean search nodes", "phase6_search_nodes.png"),
        ):
            names, vals = _group_means(benchmarks, value)
            fig, ax = plt.subplots(figsize=(9, 5))
            ax.bar(names, vals)
            ax.set_ylabel(ylabel)
            ax.set_title("Phase 6: same-depth search configuration comparison")
            ax.tick_params(axis="x", rotation=20)
            fig.tight_layout()
            target = directory / filename
            fig.savefig(target, dpi=160)
            plt.close(fig)
            paths.append(target)
    games = _read_plot(directory / "phase6_games.csv")
    if games:
        names = sorted(set(g["white_config"] for g in games) |
                       set(g["black_config"] for g in games))
        wins = [sum(g["winner_config"] == name for g in games) for name in names]
        draws = sum(g["winner_config"] == "draw" for g in games)
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.bar(names, wins)
        ax.set_ylabel("Wins (paired games)")
        ax.set_title(f"Phase 6: match wins ({len(games)} games; {draws} draws)")
        ax.tick_params(axis="x", rotation=20)
        fig.tight_layout()
        target = directory / "phase6_match_wins.png"
        fig.savefig(target, dpi=160)
        plt.close(fig)
        paths.append(target)
    moves = _read_plot(directory / "phase6_moves.csv")
    if moves:
        depth = defaultdict(list)
        for move in moves:
            depth[move["configuration"]].append(int(move["completed_depth"]))
        names = sorted(depth)
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.bar(names, [mean(depth[n]) for n in names])
        ax.set_ylabel("Mean completed search depth (plies)")
        ax.set_title("Phase 6: depth reached during complete games")
        ax.tick_params(axis="x", rotation=20)
        fig.tight_layout()
        target = directory / "phase6_game_depth.png"
        fig.savefig(target, dpi=160)
        plt.close(fig)
        paths.append(target)
    if not paths:
        print(f"No experiment CSV data found in {directory}; run benchmarks/matchups first.")
    for path in paths:
        print(f"Wrote {path}")
    return paths


def main() -> None:
    """Run consolidated experiments using one reproducible CLI."""
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    p = commands.add_parser("trace", help="Inspect iterative deepening and TT sample")
    p.add_argument("--experiment", type=int, choices=(1, 2, 3, 4), required=True)
    p.add_argument("--seed", type=int, default=33)
    p.add_argument("--empty-cells", type=int, default=19)
    p.add_argument("--max-depth", type=int, default=4)
    p.add_argument("--budget-seconds", type=float, default=4.0)

    p = commands.add_parser("benchmark", help="Same-position, same-depth search comparison")
    p.add_argument("--depth", type=int, default=3)
    p.add_argument("--repeats", type=int, default=1)
    p.add_argument("--max-branch", type=int, default=12)
    p.add_argument("--max-cells", type=int, default=14)
    p.add_argument("--output", default="experiments/results/phase6_benchmark.csv")

    p = commands.add_parser("matchups", help="Colour-swapped baseline vs TT/ordering games")
    p.add_argument("--pairs", type=int, default=2)
    p.add_argument("--budget-seconds", type=float, default=10.0)
    p.add_argument("--max-depth", type=int, default=4)
    p.add_argument("--seed-start", type=int, default=2026)
    p.add_argument("--output-dir", default="experiments/results")

    p = commands.add_parser("strength", help="Colour-swapped depth-4 vs enhanced depth-6 games")
    p.add_argument("--pairs", type=int, default=10)
    p.add_argument("--seconds", type=float, default=10.0)
    p.add_argument("--seed-start", type=int, default=2026)
    p.add_argument("--output", default="experiments/results/strength_matchups.csv")

    p = commands.add_parser("summary", help="Summarize measured experiment CSVs")
    p.add_argument("--result-dir", default="experiments/results")
    p = commands.add_parser("plots", help="Create figures from measured experiment CSVs")
    p.add_argument("--result-dir", default="experiments/results")

    args = parser.parse_args()
    if args.command == "trace":
        def log(event):
            if event["kind"] == "iteration":
                r = event["row"]
                print(f"Depth {r['depth']}: {r['best_turn']} | Eval {r['evaluation']:+.2f} | "
                      f"Nodes {r['nodes']} | Cutoffs {r['cutoffs']} | TT hits {r['tt_hits']}")
        report = run_experiment(args.experiment, seed=args.seed, empty_cells=args.empty_cells,
                                max_depth=args.max_depth, budget_seconds=args.budget_seconds,
                                on_event=log)
        print("Result:", report["result"])
        print("JSON:", report["saved_json"])
    elif args.command == "benchmark":
        benchmark(depth=args.depth, repeats=args.repeats, max_branch=args.max_branch,
                  max_cells=args.max_cells, output=args.output)
    elif args.command == "matchups":
        run_matchups(pairs=args.pairs, budget_seconds=args.budget_seconds,
                     max_depth=args.max_depth, seed_start=args.seed_start,
                     output_dir=args.output_dir)
    elif args.command == "strength":
        run_strength(pairs=args.pairs, seconds=args.seconds, seed_start=args.seed_start,
                     output=args.output)
    elif args.command == "summary":
        summarize(args.result_dir)
    elif args.command == "plots":
        plot(args.result_dir)


if __name__ == "__main__":
    main()
