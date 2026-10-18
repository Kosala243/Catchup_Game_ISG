# Catchup project architecture (technical source reference)

This is a factual code-reference document for developers and testers, **not a presentation or spoken script**.

## Rules and representation

- `src/board/coordinates.py`: 61 valid cells on a side-length-five hexagonal grid, with notation A–I and rows 1–9; six possible neighbour directions.
- `src/board/board.py`: a dictionary maps a coordinate pair to `W`, `B` or `None`.
- `src/board/groups.py`: connected components found by traversal, with descending group sizes.
- `src/game/state.py`: player to move, largest-group scores (initialized to 1), opening flag, last-turn score increase and an undo history. A turn is a list of 1–3 distinct cells placed simultaneously as a complete action.
- `src/game/rules.py`: Catchup score-increase-dependent bonus of up to three stones and lexicographic full-game group-size tie-breaking.
- `src/persistence/save_load.py`: atomic JSON save/restore, history replay validation, and a separate tournament-session record including AI clock information.

## Search and evaluation

- `src/engine/search.py`: depth-limited alpha-beta search with iterative deepening, a deadline and make/undo. Each ply is one **complete turn**. The final move comes from the deepest fully completed iteration; fallback is a legal one-stone move.
- `src/engine/move_generation.py`: exhaustive unordered combinations of legal cells for small exact tests, or a capped candidate list ranked by local features in normal play.
- `src/engine/evaluation.py`: terminal win/loss/draw from official group-size comparisons; intermediate scores based on largest and second-largest components, number of stones, frontier and a three-stone-turn opportunity.
- `src/engine/transposition_table.py`: two exact occupancy bitmasks plus rule and search configuration as the key. Entries carry depth, value and alpha-beta bound type. Capacity is bounded and uses FIFO eviction with depth-preferred replacement for the same key.
- `src/engine/move_ordering.py`: existing candidate ordering with PV, killer and history features. These only reorder the selected candidates; they cannot recover excluded moves.
- `src/engine/time_manager.py`, `src/engine/player.py`: per-game monotonic clocks and conservative per-turn search budget allocation. The whole-game budget defaults to 600 seconds per AI.

## Modes and interface

- `main.py`: CLI mode selection (`gui`, `selfplay`, `tournament`).
- `src/modes/human_vs_ai.py`: human vs AI with undo/restart.
- `src/modes/self_play.py`: both graphical AI-vs-AI controller and headless `play_one_game()`.
- `src/modes/tournament_mode.py`: terminal move relay, opponent-entry correction and session recovery.
- `src/gui/app.py`, `hex_renderer.py`, `layout.py`: Pygame controls, rendering and hex-to-screen mapping.
- `src/gui/ai_worker.py`: AI searches a copied GameState in a worker thread and returns a completed turn to the UI; the UI owns the live GameState.

## What is and is not established by experiments

The measured Phase 6 summary committed on 18 October 2026 describes 60 search measurements and 20 games (10 colour-swapped pairs):

- Mean search time: baseline **0.0803 s**; TT + ordering **0.0807 s** in those benchmark positions.
- Mean visited nodes: baseline **245.0**; TT + ordering **244.3**.
- Recorded match results: baseline **11 wins**, TT + ordering **9 wins**, no draws or forfeits.
- Across the recorded moves, completed depth averages: baseline **3.77**, TT + ordering **3.97**.

These samples demonstrate the experiment pipeline but **do not establish increased playing strength or statistically significant performance differences**. Assessments should be based on verified code, genuinely measured results and the official target environment.

## Known limitations and considerations

1. The default candidate set is **selective** and can miss a globally best complete turn.
2. The current board representation and connected-group traversal are correctness-oriented, not maximally optimized for very large search trees.
3. Cooperative cancellation may exceed a deadline slightly due to work between checks; whole-game performance must be demonstrated on Windows 11.
4. A `.bat` launcher runs Python source; it is not a native Windows executable.
5. Tournament save/restore records and clocks should be tested together; legacy sessions without clock metadata are deliberately rejected for safe resume.
6. GUI behaviour, graphics, keyboard controls and path handling need manual Windows 11 verification.

See `AI_USAGE.md` for limitations on what may legitimately be used in the graded assignment.
