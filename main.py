"""Catchup launcher: human GUI, headless/visual self-play and tournament relay."""
import argparse

from src.board.board import BLACK, WHITE
from src.modes import human_vs_ai, self_play, tournament_mode


def main() -> None:
    parser = argparse.ArgumentParser(description="Catchup game program")
    sub = parser.add_subparsers(dest="mode", required=True)

    gui = sub.add_parser("gui", help="Human versus AI in a pygame window")
    gui.add_argument("--human-colour", choices=[WHITE, BLACK], default=WHITE)
    gui.add_argument("--think-seconds", type=float, default=600.0,
                     help="AI total thinking budget (for local demo/testing)")

    tournament = sub.add_parser("tournament", help="Terminal tournament relay")
    tournament.add_argument("--colour", choices=[WHITE, BLACK], required=True)
    tournament.add_argument("--resume", action="store_true")

    selfplay = sub.add_parser("selfplay", help="AI versus AI, headless or visual")
    selfplay.add_argument("--gui", action="store_true", help="Show animated pygame board")
    selfplay.add_argument("--think-seconds", type=float, default=600.0,
                          help="Per-AI total thinking budget (for demo/testing)")
    selfplay.add_argument("--delay-ms", type=int, default=400,
                          help="Delay between AI turns in visual mode (default: 400ms)")

    args = parser.parse_args()
    if args.mode in ("gui", "selfplay") and not (0 < args.think_seconds <= 600):
        parser.error("--think-seconds must be greater than 0 and at most 600")
    if args.mode == "gui":
        human_vs_ai.run(human_colour=args.human_colour, think_seconds=args.think_seconds)
    elif args.mode == "tournament":
        tournament_mode.run(my_colour=args.colour, resume=args.resume)
    elif args.mode == "selfplay":
        if args.gui:
            self_play.run(think_seconds=args.think_seconds, delay_ms=args.delay_ms)
        else:
            print(self_play.play_one_game(think_seconds=args.think_seconds))


if __name__ == "__main__":
    main()
