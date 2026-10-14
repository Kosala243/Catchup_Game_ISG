# Generative AI / Open-Source Usage Disclosure

Per the ISG assignment rules, generative AI must not be used to write the
search engine, evaluation function, or state-action representation, and any
use of GenAI or external/open-source code must be disclosed here.

## What was AI-assisted

Claude Code was used on 2026-09-12 to scaffold the initial project structure:
directory layout, file skeletons, pygame GUI plumbing, CLI entry point,
save/load, and the test/experiment harness wiring.

The following files also contain **placeholder logic** generated with AI
assistance, purely so the project would run end-to-end during scaffolding.
These are explicitly **not** the final submitted algorithm and must be
replaced with your own work before submission (or, if any part is kept, that
must be disclosed explicitly below with specifics):

- `src/board/coordinates.py` - coordinate system / neighbour geometry
- `src/board/board.py`, `src/board/groups.py` - board & group-size representation
- `src/game/rules.py`, `src/game/state.py` - turn rules and GameState
- `src/engine/search.py` - **random-move placeholder**, not alpha-beta
- `src/engine/evaluation.py` - trivial score-difference placeholder
- `src/engine/transposition_table.py`, `move_ordering.py`, `time_manager.py` - stubs/placeholders

## What was NOT AI-assisted

(Fill in as you replace the above with your own implementation, e.g. "the
alpha-beta search in src/engine/search.py, written from scratch on [date],
no AI assistance.")

## Open-source / third-party code

- `pygame`, `numpy` - used only as pre-installed runtime libraries per the
  assignment's rules, not vendored/copied code.
- (list any other external code/snippets used, with source, here)
