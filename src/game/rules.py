"""
Here the compulsory single-stone White opening is handled by GameState.
"""
from itertools import zip_longest
from typing import List

def max_stones_allowed(
    mover_score: int,
    opponent_score: int,
    opponent_score_increased: bool,
) -> int:
    return 3 if opponent_score_increased and opponent_score >= mover_score else 2

def compare_group_lists(a_groups: List[int], b_groups: List[int]) -> int:
    a = sorted(a_groups, reverse=True)
    b = sorted(b_groups, reverse=True)
    for a_size, b_size in zip_longest(a, b, fillvalue=0):
        if a_size != b_size:
            return 1 if a_size > b_size else -1
    return 0
