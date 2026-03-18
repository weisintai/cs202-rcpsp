# CP Backend

This is the experimental CP-style backend.

## Purpose

- provide a separate branch-and-propagate architecture
- make CP-style changes without destabilizing the accepted heuristic backend

## Layout

- `state.py`
  - CP node and explanation dataclasses
- `propagation.py`
  - EST/LST tightening, timetable propagation, forced pair-order inference
- `search.py`
  - branching policy, incumbent management, and DFS orchestration
- `solver.py`
  - thin public wrapper and compatibility exports

## Scope

This backend currently owns:

- CP node state over resource-ordering decisions
- temporal propagation under added order edges
- incumbent-based latest-start bounds
- compulsory-part / timetable pruning on EST/LST windows
- limited forced pair-order propagation from EST/LST windows on larger instances
- explicit timetable-overload explanations
- pairwise conflict branching from resource explanations
- a hybrid-guided warm-start phase that gives CP search a stronger incumbent bound

It is currently a scaffold, not the accepted main solver. Changes here should target `stronger propagation and branching`, not heuristic polishing.
