"""Regression tests for the observational experiment dashboard backend."""
import csv
import json
from threading import Event

import pytest

from experiments.catchup_diagnostics import EXPERIMENTS, get_experiment, run_experiment
from experiments.phase6_common import build_position, fingerprint
from src.game.notation import parse_turn


def demo(number, tmp_path, **kwargs):
    return run_experiment(number, seed=35, empty_cells=7, max_depth=2,
                          budget_seconds=3.0, output_dir=tmp_path, **kwargs)


def test_four_buttons_use_phase6_configs():
    assert [(e.number, e.configuration, e.use_tt, e.use_ordering)
            for e in EXPERIMENTS] == [
        (1, "baseline", False, False),
        (2, "ordering_only", False, True),
        (3, "tt_only", True, False),
        (4, "tt_and_ordering", True, True),
    ]
    with pytest.raises(ValueError):
        get_experiment(5)


@pytest.mark.parametrize("number", [1, 2, 3, 4])
def test_each_experiment_reports_real_depths_and_legal_turns(number, tmp_path):
    state = build_position(35, 7)
    original = fingerprint(state)
    events = []
    report = demo(number, tmp_path, on_event=events.append)
    assert fingerprint(state) == original
    assert [row["depth"] for row in report["iterations"]] == [1, 2]
    assert [row["completed_depth"] for row in report["iterations"]] == [1, 2]
    assert report["result"]["completed_depth"] == 2
    assert any(e["kind"] == "iteration" for e in events)
    for row in report["iterations"]:
        trial = state.copy()
        trial.apply_turn(parse_turn(row["best_turn"]))
        assert len(trial.history) == len(state.history) + 1
        assert row["nodes"] >= 1
        assert row["elapsed_seconds"] >= 0
    file = json.loads((tmp_path / __import__("pathlib").Path(report["saved_json"]).name).read_text())
    assert file["result"]["best_turn"] == report["result"]["best_turn"]
    with open(report["saved_csv"], newline="", encoding="utf-8") as stream:
        assert len(list(csv.DictReader(stream))) == 2


@pytest.mark.parametrize("number", [3, 4])
def test_tt_real_entries_and_bound_counts(number, tmp_path):
    r = demo(number, tmp_path)
    summary = r["tt_summary"]
    assert summary["size"] > 0
    assert summary["size"] == summary["exact"] + summary["lower"] + summary["upper"]
    assert summary["capacity"] == 50000
    assert len(r["tt_preview"]) <= 25
    for entry in r["tt_preview"]:
        assert entry["bound"] in ("exact", "lower", "upper")
        assert 0 <= entry["white_stones"] + entry["black_stones"] <= 61
        assert (int(entry["white_mask"], 16) & int(entry["black_mask"], 16)) == 0
        assert entry["to_move"] in ("W", "B")
        assert 1 <= entry["depth"] <= 2


@pytest.mark.parametrize("number", [1, 2])
def test_no_tt_is_truthfully_empty(number, tmp_path):
    r = demo(number, tmp_path)
    assert r["tt_summary"]["size"] == 0
    assert r["tt_preview"] == []
    assert all(row["tt_hits"] == 0 for row in r["iterations"])


def test_fixed_depth_values_agree_across_all_four_configs(tmp_path):
    values = []
    for number in range(1, 5):
        r = demo(number, tmp_path)
        values.append(r["iterations"][-1]["evaluation"])
    assert all(v == pytest.approx(values[0]) for v in values)


def test_cancel_before_begin_returns_legal_fallback(tmp_path):
    stop = Event()
    stop.set()
    r = demo(4, tmp_path, cancel=stop)
    assert r["iterations"] == []
    assert r["result"]["cancelled"]
    assert r["result"]["fallback_used"]
    state = build_position(35, 7)
    state.apply_turn(parse_turn(r["result"]["best_turn"]))


def test_zero_budget_is_not_falsely_reported_as_completed(tmp_path):
    r = run_experiment(4, seed=35, empty_cells=7, max_depth=3,
                       budget_seconds=0, output_dir=tmp_path)
    assert r["result"]["completed_depth"] == 0
    assert r["result"]["timed_out"]
    assert r["saved_csv"] is None


@pytest.mark.parametrize("options", [
    {"empty_cells": 0}, {"empty_cells": 61}, {"max_depth": 0},
    {"max_cells": 0}, {"max_branch": -1}, {"budget_seconds": float("nan")},
    {"tt_preview_limit": 101}, {"seed": "33"},
])
def test_reject_invalid_settings(options, tmp_path):
    defaults = dict(seed=35, empty_cells=7, max_depth=2,
                    budget_seconds=1, output_dir=tmp_path)
    defaults.update(options)
    with pytest.raises(ValueError):
        run_experiment(1, **defaults)


def test_dashboard_module_imports_without_pygame_at_module_import():
    from experiments.catchup_dashboard import main, run
    assert callable(run) and callable(main)
