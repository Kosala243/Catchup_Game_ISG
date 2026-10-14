"""
Batch self-play runs for comparing engine configurations (depth, heuristics,
enhancements). Uses matplotlib/pandas-style tooling that is NOT part of the
shipped program's runtime dependencies - see requirements-dev.txt.

SCAFFOLDING NOTE: only wired up against the placeholder random-move engine for
now. Extend this once your real search/evaluation exist, e.g. by parametrising
AIPlayer/search.choose_move with different configs to compare.
"""

import csv
import os

from src.modes.self_play import play_one_game

RESULTS_PATH = "experiments/results/results.csv"


def run(num_games: int = 20) -> None:
    os.makedirs(os.path.dirname(RESULTS_PATH), exist_ok=True)
    with open(RESULTS_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["game", "winner", "white_score", "black_score", "turns"])
        writer.writeheader()
        for i in range(num_games):
            result = play_one_game()
            writer.writerow({
                "game": i,
                "winner": result["winner"],
                "white_score": result["final_scores"]["W"],
                "black_score": result["final_scores"]["B"],
                "turns": result["turns"],
            })
    print(f"Wrote {num_games} games to {RESULTS_PATH}")


if __name__ == "__main__":
    run()
