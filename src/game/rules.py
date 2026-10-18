"""Pure Catchup turn-limit and terminal group-comparison rules.

The compulsory single-stone White opening is handled by GameState.
"""
from itertools import zip_longest
from typing import List


def max_stones_allowed(
    mover_score: int,
    opponent_score: int,
    opponent_score_increased: bool,
) -> int:
    """Return 3 only when the previous turn earned the opponent's bonus.

    On every non-opening turn the mover may place one or two stones, or up to
    three when the previous mover grew their largest group and the new score
    is at least the current mover's score.
    """
    return 3 if opponent_score_increased and opponent_score >= mover_score else 2


def compare_group_lists(a_groups: List[int], b_groups: List[int]) -> int:
    """Compare entire group-size multisets, descending, as Catchup requires.

    Every tied group participates, including repeated groups of the same size.
    Missing groups are compared as zero. Returns 1, -1, or 0.
    No board or score state is mutated.
    """
    a = sorted(a_groups, reverse=True)
    b = sorted(b_groups, reverse=True)
    for a_size, b_size in zip_longest(a, b, fillvalue=0):
        if a_size != b_size:
            return 1 if a_size > b_size else -1
    return 0
