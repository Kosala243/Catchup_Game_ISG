# Design Notes (source material for the presentation video)

Fill this in as you build the real engine - it should end up covering
everything the video needs to explain.

## Board & Coordinate Representation
- How cells are stored, why, and any performance-driven changes from the
  scaffolded `dict`-based `Board`.

## State-Action Representation
- How a "turn" (1-3 stone placements) is represented and generated.
- Any incremental update tricks (group sizes, hashing) and why they matter.

## Search
- Alpha-beta details: move ordering, transposition table (hash scheme,
  indexing, replacement policy), iterative deepening / time management.

## Evaluation Function
- What it computes and why; alternatives considered and rejected.

## Experiments
- What was compared (e.g. with/without TT, different depths/heuristics),
  how (self-play, `experiments/run_experiments.py`), and the results
  (`experiments/plots.py` output goes here or in the slides).
