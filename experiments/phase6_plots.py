"""Create noninteractive PNG charts from actual Phase 6 experiment CSVs.

Run: python -m experiments.phase6_plots
Requires matplotlib only for development (requirements-dev.txt).
"""
import argparse
import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean


def _read(path):
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
    benchmarks = _read(directory / "phase6_benchmark.csv")
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
    games = _read(directory / "phase6_games.csv")
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
    moves = _read(directory / "phase6_moves.csv")
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


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--result-dir", default="experiments/results")
    args = p.parse_args()
    plot(args.result_dir)


if __name__ == "__main__":
    main()
