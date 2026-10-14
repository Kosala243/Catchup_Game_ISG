"""
Plotting for the presentation video. Dev-only (matplotlib is in
requirements-dev.txt, not shipped with the program).
"""

import csv

import matplotlib.pyplot as plt

RESULTS_PATH = "experiments/results/results.csv"


def plot_win_rate_by_colour(path: str = RESULTS_PATH) -> None:
    wins = {"W": 0, "B": 0, "draw": 0}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            winner = row["winner"] if row["winner"] in ("W", "B") else "draw"
            wins[winner] += 1

    plt.bar(wins.keys(), wins.values())
    plt.title("Wins by colour")
    plt.ylabel("Games")
    plt.savefig("experiments/results/win_rate.png")
    plt.show()


if __name__ == "__main__":
    plot_win_rate_by_colour()
