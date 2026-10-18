"""Summarize REAL Phase 6 CSV results. No synthetic scores or win rates.

Run: python -m experiments.phase6_summary
"""
import argparse
import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean


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


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--result-dir", default="experiments/results")
    args = p.parse_args()
    summarize(args.result_dir)


if __name__ == "__main__":
    main()
