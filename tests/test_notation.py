from src.game.notation import format_turn, parse_turn


def test_round_trip_single_stone():
    turn = [(0, 1)]
    assert parse_turn(format_turn(turn)) == turn


def test_round_trip_multi_stone():
    turn = [(0, 1), (4, 5), (8, 9)]
    assert parse_turn(format_turn(turn)) == turn
