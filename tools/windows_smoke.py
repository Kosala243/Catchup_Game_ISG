"""Run a short, headless end-to-end game from an extracted release.

Uses the actual main.py CLI, not a mocked engine. GUI still needs a manual
window-and-controls test on Windows 11 with pygame installed.
"""
from __future__ import annotations

import ast
import argparse
from pathlib import Path
import subprocess
import sys


def validate_result(raw: str) -> dict:
    """Find and validate the terminal game summary without evaluating code."""
    final_line = next((line for line in reversed(raw.splitlines())
                       if line.strip().startswith("{'winner':")), None)
    if final_line is None:
        raise ValueError("No game result dictionary printed")
    result = ast.literal_eval(final_line.strip())
    if not isinstance(result, dict):
        raise ValueError("Game result is not a dictionary")
    if result.get("winner") not in ("W", "B", None):
        raise ValueError("Invalid winning colour")
    scores = result.get("final_scores")
    if not isinstance(scores, dict) or set(scores) != {"W", "B"}:
        raise ValueError("Missing game scores")
    if not all(isinstance(scores[k], int) and scores[k] >= 1 for k in scores):
        raise ValueError("Invalid game score")
    if not isinstance(result.get("turns"), int) or result["turns"] < 1:
        raise ValueError("Invalid number of turns")
    for key in ("white_time_left", "black_time_left"):
        left = result.get(key)
        if not isinstance(left, (int, float)) or not (0 <= left <= 600):
            raise ValueError(f"Invalid AI clock: {key}")
    return result


def smoke(root: Path, budget_seconds: float = 2.0, timeout_seconds: float = 90.0) -> dict:
    """CLI integration smoke test with a small *whole-game* time budget."""
    if not (0 < budget_seconds <= 600):
        raise ValueError("budget_seconds must be in (0, 600]")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    process = subprocess.run(
        [sys.executable, "main.py", "selfplay", "--think-seconds", str(budget_seconds)],
        cwd=root, text=True, capture_output=True, timeout=timeout_seconds,
        check=False,
    )
    if process.returncode != 0:
        raise RuntimeError(f"Self-play crashed (exit {process.returncode}):\n{process.stderr}")
    outcome = validate_result(process.stdout)
    for clock in ("white_time_left", "black_time_left"):
        if outcome[clock] > budget_seconds + 1e-6:
            raise ValueError("AI time incorrectly exceeded the initial whole-game budget")
    return outcome


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--budget-seconds", type=float, default=2.0)
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    try:
        result = smoke(root, args.budget_seconds, args.timeout_seconds)
    except (ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(f"PASS: One complete game ({result['turns']} turns); "
          f"winner={result['winner']}, scores={result['final_scores']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
