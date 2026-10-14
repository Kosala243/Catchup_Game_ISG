# Catchup (KEN4123 Intelligent Search & Games)

An alpha-beta based engine for the two-player game Catchup, plus a pygame
board for local play and a relay mode for the onsite tournament.

## Requirements

- Python 3.10.7
- `pip install -r requirements.txt` (pygame, numpy - the only runtime deps,
  matching what's guaranteed on the tournament machines)
- `pip install -r requirements-dev.txt` for running experiments/plots (not
  needed to run the game itself)

## Running

```
python main.py gui                      # local human-vs-AI, pygame board
python main.py tournament --colour W    # tournament relay mode (see below)
python main.py selfplay                 # one headless AI-vs-AI game
```

On Windows, `run.bat` wraps `python main.py` with any arguments.

## Tournament mode

Your program plays one colour. When it's the opponent's turn, type their move
in cell notation (e.g. `D5` or `D5 E6` for a two-stone turn) and press enter.
Your own moves are printed so you can relay them back. The game state
autosaves after every turn to `saves/current_game.json`; pass `--resume` to
continue from there after a crash. Type `undo` instead of a move to take back
the last turn.

## Coordinates

Cells are labelled exactly as in Figure 2 of the rules PDF: columns A-I, rows
1-9, 61 cells total (a hexagon with 5 cells per side).

## Project layout

See `docs/design_notes.md` for the write-up this project's video is based on.
Directory-by-directory purpose:

- `src/board/` - board state, coordinates, connected-group sizes
- `src/game/` - turn/scoring rules, GameState (undo), move notation
- `src/engine/` - search, evaluation, transposition table, time management
- `src/gui/` - pygame rendering and input
- `src/modes/` - the three ways to run a game (local GUI, tournament relay, headless self-play)
- `src/persistence/` - save/restore for crash recovery
- `experiments/`, `tests/` - as named
- `docs/`, `video/` - write-up and submission materials

## Status

Project scaffolding only so far - see `AI_USAGE.md`. The board/rules layer is
a working placeholder; `src/engine/search.py`'s alpha-beta is not yet
implemented (currently a random-move stand-in) and needs to be written.
