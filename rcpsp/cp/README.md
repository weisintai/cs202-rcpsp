# CP Backend

This is the experimental CP-style backend.

The implementation roadmap for this backend lives in [../../CP_ROADMAP.md](/Users/weisintai/development/smu/modules/y2s2/cs202/project/CP_ROADMAP.md).

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
  - backend entrypoint

## Scope

This backend currently owns:

- CP node state over resource-ordering decisions
- temporal propagation under added order edges
- incumbent-based latest-start bounds
- compulsory-part / timetable pruning on EST/LST windows
- limited forced pair-order propagation from EST/LST windows on larger instances
- explicit timetable-overload explanations
- a medium-budget failure cache over monotone pair-order sets
- pairwise conflict branching from resource explanations
- a local guided-seed warm-start phase that gives CP search a stronger incumbent bound

It is currently a scaffold, not the accepted main solver. Changes here should target `stronger propagation and branching`, not heuristic polishing.

## Current Direction

This backend is now following a stricter route:

- stay self-contained inside `rcpsp/cp`
- use `guided_seed` only as a local incumbent/proof helper
- improve the backend through stronger propagation, explanations, and branching
- accept changes only against the `cp_acceptance` matrix from [../../CP_ROADMAP.md](/Users/weisintai/development/smu/modules/y2s2/cs202/project/CP_ROADMAP.md)
