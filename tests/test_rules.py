from src.game.rules import compare_group_lists, max_stones_allowed


def test_no_bonus_when_scores_equal_and_not_increased():
    assert max_stones_allowed(mover_score=3, opponent_score=3, opponent_score_increased=False) == 2


def test_bonus_when_opponent_caught_up():
    assert max_stones_allowed(mover_score=2, opponent_score=3, opponent_score_increased=True) == 3


def test_no_bonus_if_opponent_still_behind():
    assert max_stones_allowed(mover_score=5, opponent_score=3, opponent_score_increased=True) == 2


def test_tie_break_example_from_rules_pdf():
    # Player A: {6, 5, 5, 3, ...}, Player B: {6, 5, 4, 3, ...} -> A wins on 3rd group.
    assert compare_group_lists([6, 5, 5, 3], [6, 5, 4, 3]) == 1
