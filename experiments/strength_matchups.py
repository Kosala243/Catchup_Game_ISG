"""Colour-swapped strength experiment: depth-4 selective versus depth-6 enhanced.

Uses the SAME official Catchup rules, candidate generator and evaluation
function for both competitors. A has selective search depth 4 with no
automatic full-width endgame and no cross-turn cache; B uses depth 6,
exact move generation at <=7 empties, and a persistent bounded table.
Results are measurements, not guaranteed improvements.

Run: python -m experiments.strength_matchups --pairs 10 --seconds 10
"""
import argparse
import csv
from dataclasses import dataclass
import math
from pathlib import Path
import random

from src.board.board import BLACK, WHITE, other
from src.engine.search import SearchStats, iterative_deepening
from src.engine.time_manager import Clock, allocate_time
from src.engine.move_ordering import MoveOrdering
from src.engine.transposition_table import TranspositionTable
from src.game.state import GameState


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


def run(pairs=10, seconds=10.0, seed_start=2026, output='experiments/results/strength_matchups.csv'):
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pairs', type=int, default=10)
    parser.add_argument('--seconds', type=float, default=10)
    parser.add_argument('--seed-start', type=int, default=2026)
    parser.add_argument('--output', default='experiments/results/strength_matchups.csv')
    options = parser.parse_args()
    run(options.pairs, options.seconds, options.seed_start, options.output)


if __name__ == '__main__':
    main()
