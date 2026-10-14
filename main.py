"""
Entry point. Usage:
    python main.py gui                      # local human-vs-AI with pygame board
    python main.py tournament --colour W    # tournament relay mode
    python main.py selfplay                 # one headless AI-vs-AI game
"""

import argparse

from src.board.board import BLACK, WHITE
from src.modes import human_vs_ai, self_play, tournament_mode


def main() -> None:
    parser = argparse.ArgumentParser(description="Catchup game program")
    sub = parser.add_subparsers(dest="mode", required=True)

    gui_parser = sub.add_parser("gui", help="Local human-vs-AI play with the pygame board")
    gui_parser.add_argument("--human-colour", choices=[WHITE, BLACK], default=WHITE)

    tourn_parser = sub.add_parser("tournament", help="Tournament relay mode")
    tourn_parser.add_argument("--colour", choices=[WHITE, BLACK], required=True)
    tourn_parser.add_argument("--resume", action="store_true")

    sub.add_parser("selfplay", help="One headless AI-vs-AI game")

    args = parser.parse_args()

    if args.mode == "gui":
        human_vs_ai.run(human_colour=args.human_colour)
    elif args.mode == "tournament":
        tournament_mode.run(my_colour=args.colour, resume=args.resume)
    elif args.mode == "selfplay":
        result = self_play.play_one_game()
        print(result)


if __name__ == "__main__":
    main()
