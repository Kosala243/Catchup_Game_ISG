"""Fast, headless verification of the Catchup launcher/search upgrade.

Run: python -m tools.check_live_features
For Pygame visuals, manually check `python main.py` as well.
"""
from __future__ import annotations

import math
import sys
from unittest.mock import patch

from experiments.lab import build_position, compare_profiles, fingerprint
from src.board.board import WHITE, BLACK
from src.engine.evaluation import ABLATION_VARIANTS, active_evaluation_variant, evaluate, evaluation_variant
from src.engine.search import SearchStats, alpha_beta, capture_search_progress, iterative_deepening
from src.engine.transposition_table import position_key, TranspositionTable
from src.game.state import GameState


def run():
    original = build_position(33, 19)
    before = fingerprint(original)
    normal = SearchStats()
    tactical = SearchStats()
    a_value, a_move = alpha_beta(original, 1, -math.inf, math.inf, original.to_move,
                                 stats=normal, tactical_extensions=0)
    b_value, b_move = alpha_beta(original, 1, -math.inf, math.inf, original.to_move,
                                 stats=tactical, tactical_extensions=1)
    assert normal.tactical_extensions == 0
    assert tactical.tactical_extensions > 0, "This seeded position must trigger tactical extensions"
    assert fingerprint(original) == before
    for move in (a_move, b_move):
        trial = original.copy()
        trial.apply_turn(move)
        assert len(trial.history) == len(original.history) + 1
    print(f"Tactical extension: {tactical.tactical_extensions} extensions in depth-1 search")

    events = []
    with capture_search_progress(events.append):
        chosen = iterative_deepening(original, 1.5, original.to_move, max_depth=3)
    assert events and events[0]["depth"] == 1
    assert [e["depth"] for e in events] == list(range(1, len(events) + 1))
    assert all(e["total"]["nodes"] > 0 and e["tt_size"] >= 0 for e in events)
    trial = original.copy()
    trial.apply_turn(chosen)
    print(f"Live events: {len(events)} completed iterations; latest {events[-1]['best_turn']}")
    assert fingerprint(original) == before

    base_key = position_key(original, original.to_move, 12, 14, False)
    extended_key = position_key(original, original.to_move, 12, 14, False,
                                extensions_left=1)
    ablated_key = position_key(original, original.to_move, 12, 14, False,
                               evaluation_id="no_bridges")
    assert len({base_key, extended_key, ablated_key}) == 3
    for variant in ABLATION_VARIANTS:
        with evaluation_variant(variant):
            assert active_evaluation_variant() == variant
            left = evaluate(original, WHITE)
            right = evaluate(original, BLACK)
            assert left == -right
    assert active_evaluation_variant() == "full"
    print(f"TT key isolation: OK; {len(ABLATION_VARIANTS)} evaluator variants checked")

    # CLI GUI selector is replaceable without removing any original CLI paths.
    import main
    with patch("sys.argv", ["main.py"]), \
         patch("src.gui.launcher.run", return_value={"mode": "gui", "colour": WHITE,
                                                       "think_seconds": 12.0}), \
         patch.object(main.human_vs_ai, "run") as run_gui:
        main.main()
        run_gui.assert_called_once_with(human_colour=WHITE, think_seconds=12.0)
    with patch("sys.argv", ["main.py", "selfplay", "--gui", "--think-seconds", "12"]), \
         patch.object(main.self_play, "run") as selfplay:
        main.main()
        selfplay.assert_called_once_with(think_seconds=12.0, delay_ms=400)
    print("Graphical launcher dispatch + original CLI dispatch: OK")
    print("PASS: live search, tactical extension, evaluator ablations, TT isolation, launcher")


if __name__ == "__main__":
    run()
