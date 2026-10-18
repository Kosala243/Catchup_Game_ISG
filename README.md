# Catchup — Intelligent Search & Games (KEN4123)

A Python implementation of the two-player board game **Catchup** with an alpha-beta search engine, a Pygame interface, terminal tournament relay, persistent tournament sessions, and tools for testing and performance experiments.

## Requirements

- **Python 3.10 or newer** for running the source code. The designated Windows assessment environment uses **Python 3.10.7**.
- **Pygame 2.5+ (below 3.0)** for the graphical modes. No other third-party library is imported by the game at runtime.
- Windows, macOS, or Linux for local development. The Windows launcher (`run.bat`) specifically checks for Python **3.10.x**.

From the project root, install the runtime dependency on a machine with internet access:

```bash
python -m pip install -r requirements.txt
```

For tests and plots, install the separate development dependencies:

```bash
python -m pip install -r requirements-dev.txt
```

Do not assume you can install packages on an offline assessment computer; use its available Python and Pygame installations.

## Run the game

Run these commands **from the repository root** (the folder containing `main.py`). On macOS, use `python3` if `python` is not available.

| Mode | Command | Interface |
| --- | --- | --- |
| Human vs AI — human plays White | `python main.py gui --human-colour W` | Pygame |
| Human vs AI — human plays Black | `python main.py gui --human-colour B` | Pygame |
| AI vs AI — graphical | `python main.py selfplay --gui` | Pygame |
| AI vs AI — graphical, short demo | `python main.py selfplay --gui --think-seconds 12 --delay-ms 150` | Pygame |
| AI vs AI — headless | `python main.py selfplay` | Terminal |
| Tournament — engine plays White | `python main.py tournament --colour W` | Terminal |
| Tournament — engine plays Black | `python main.py tournament --colour B` | Terminal |
| Resume an existing tournament game | `python main.py tournament --colour B --resume` | Terminal |

Use the **same colour as the saved game** when resuming. `--think-seconds` in the `gui` and `selfplay` modes sets the **total thinking-time allowance per AI for the whole game**, not time per move. The default is 600 seconds (10 minutes). `--delay-ms` controls the pause between turns in *graphical self-play only*.

On Windows 11 with Python 3.10.x, use the batch launcher instead:

```bat
run.bat gui --human-colour W
run.bat selfplay --gui --think-seconds 12 --delay-ms 150
run.bat tournament --colour B
```

`run.bat` changes to its own directory before launching the program. For a local Python version other than 3.10.x, run `python main.py ...` directly instead of the batch file.

### Pygame controls

| Input | Action |
| --- | --- |
| Left-click an empty hex | Select a cell to place a stone |
| Enter or **Confirm** | Submit the selected cells before reaching the maximum allowed |
| Select the maximum number of cells | Automatically submit that turn |
| Backspace, Escape, or right-click | Remove the most recently selected cell |
| **Clear** | Remove the pending selection |
| **U** or **Undo** | Undo the latest applicable turn(s) |
| **R** or **Restart** | Start a new game |
| Space or **Pause** | Pause/resume **graphical AI-vs-AI** play |

In human-vs-AI mode, you cannot place stones while the AI is thinking. Undo returns to the position before the latest human turn and any AI reply. In graphical self-play, undo removes the last AI turn and leaves playback paused. Thinking time already used is not refunded.

### Headless self-play output

The terminal prints a dictionary containing `winner`, `final_scores`, `turns`, `white_time_left`, and `black_time_left`. The final scores are the **largest connected-group sizes**, not the total number of stones placed.

### Tournament relay (terminal only)

Tournament mode does **not** open a Pygame window. Your program plays the selected colour; you enter the opponent's complete turn, and the engine prints its response.

At an opponent prompt, enter one to three space-separated cell labels, for example:

```text
Opponent (W) move: E5
My move: D5 E6
Opponent (W) move: C4 D4
```

The actual number of legal stones is determined by the current Catchup position. At the opponent prompt, the following commands are available:

- `status` — display current scores, player to move, and remaining engine time.
- `undo` — retract the previous opponent entry **and** the engine's response, when a complete exchange exists; thinking time is not restored.
- `help` — show input instructions.
- `quit` — save the session and exit.

Tournament sessions are automatically saved to `saves/current_game.json`. To continue after an interruption, use `--resume` with the original colour. The session contains the board and remaining thinking time; an unfinished search may have a conservative time reservation charged on recovery. Starting a tournament without `--resume` creates a new game and replaces the current autosave.

## Catchup rules implemented

- A **61-cell hexagonal board**, with five cells per side; coordinates use columns **A–I** and rows **1–9**.
- White opens by placing **exactly one** stone. That opening placement does not count as a score increase.
- Subsequent turns may place **one or two** stones, or **up to three** when the previous player's largest-group score increased on their turn and is at least as large as the next player's score.
- A player's score is the size of their **largest connected group**. A game ends when the board is full.
- If largest groups are tied at the end, all connected-group sizes are compared in descending order until a difference determines the winner (or the game is drawn).

A complete placement of one to three stones is a **single search ply**. The engine uses iterative deepening, alpha-beta pruning, heuristic evaluation, selective candidate ranking, move ordering, and a bounded transposition table. The default search depth limit is **4 complete turns**, subject to available thinking time. **Selective search is not a guarantee of the globally optimal move.**

## Testing

From the project root:

```bash
python -m pytest -q
python tools/check_environment.py
python tools/windows_smoke.py --budget-seconds 2
```

For a preflight on the designated Windows environment:

```bat
python tools\check_environment.py --require-windows --require-python-310 --gui
```

Pygame window appearance, clicking, keyboard controls, and tournament interaction still require manual testing on the target machine.

## Benchmarks and experiments

These tools are for development and require `requirements-dev.txt`:

```bash
python -m experiments.phase6_benchmark --depth 3 --repeats 5
python -m experiments.phase6_matchups --pairs 10 --budget-seconds 10 --max-depth 4
python -m experiments.phase6_summary
python -m experiments.phase6_plots
```

The matchup runs two games per pair, swapping the engine configurations between White and Black. Experiment CSVs and PNG plots are written to `experiments/results/`. See `docs/architecture.md` for the implementation outline and interpretation of the recorded experiments.

## Build and verify a portable source package

```bash
python tools/build_release.py
python tools/build_release.py --verify dist/Catchup_Windows_Source.zip
python tools/final_validation.py --budget-seconds 1.5 --report dist/phase8_audit.json
```

The source package is `dist/Catchup_Windows_Source.zip`. It contains a Windows batch launcher but **is not a standalone `.exe`**. The final-validation tool also checks that a short headless game runs from a cleanly extracted ZIP; some separate documentation and platform checks may still need attention.

An optional Windows executable builder is provided for a **Windows development machine** (requires PyInstaller in addition to Pygame):

```bat
python -m pip install pyinstaller
python tools\build_native_windows.py
```

The output is an **entire directory**, `dist\windows_exe\Catchup\`, containing `Catchup.exe` and its companion files. Transfer and test the whole directory, not the `.exe` alone. The Windows build has not been verified merely by running the source tests on macOS or Linux.

## Project structure

```text
Catchup_Game_ISG/
├── main.py                     # CLI entry point
├── run.bat                     # Windows Python launcher
├── requirements.txt            # Runtime dependency
├── requirements-dev.txt        # Development dependencies
├── src/
│   ├── board/                  # Board geometry and connected groups
│   ├── game/                   # Rules, turns, scoring, notation
│   ├── engine/                 # Search, evaluation, move selection, clock
│   ├── gui/                    # Pygame drawing, input, background worker
│   ├── modes/                  # Human play, self-play, tournament relay
│   └── persistence/            # Game and tournament-session saves
├── experiments/                # Reproducible benchmarks, matchups, plots
├── tests/                      # Regression and integration tests
├── tools/                      # Environment, smoke, release and audit tools
├── docs/                       # Architecture notes
└── saves/                      # Runtime tournament saves (generated)
```

See the command-line help for the latest options: `python main.py --help` and `python main.py selfplay --help`.
