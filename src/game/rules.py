"""
Catchup turn/scoring rules (KEN4123 assignment PDF).

SCAFFOLDING NOTE: encodes the rules as given; double check every clause
against the rules PDF yourself before relying on it, and treat this as a
first draft you own, not a finished, verified implementation.
"""

from typing import List


def max_stones_allowed(mover_score: int, opponent_score: int, opponent_score_increased: bool) -> int:
    """
    Highest number of stones the player to move may place this turn.
    They may always choose to place fewer (down to 1), except White's
    opening placement, which is handled separately in GameState (exactly 1).
    """
    if opponent_score_increased and opponent_score >= mover_score:
        return 3
    return 2


def compare_group_lists(a_groups: List[int], b_groups: List[int]) -> int:
    """
    Rule 3/4 tie-break: compare sorted (desc) group-size lists position by
    position; first difference decides. Returns 1 if `a` wins, -1 if `b`
    wins, 0 for a full draw.
    """
    a = sorted(a_groups, reverse=True)
    b = sorted(b_groups, reverse=True)
    for i in range(max(len(a), len(b))):
        av = a[i] if i < len(a) else 0
        bv = b[i] if i < len(b) else 0
        if av != bv:
            return 1 if av > bv else -1
    return 0
