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

## Current 30s Read

The current accepted baseline is strong on public-size instances and the active experimental direction is now `deep-budget-only` improvement rather than more `0.1s` tuning.

Current reference point:

- `sm_j10 @ 1.0s`: perfect
- `sm_j20 @ 1.0s`: `155/158` exact
- `sm_j30 @ 1.0s`: `114/120` exact

Recent `30s` CP sampling on held-out large instances showed that the deeper-budget path is the right place to keep experimenting:

- `testset_ubo100` 10-instance sample:
  - `8 feasible / 1 infeasible / 1 unknown`
  - solved bounded cases averaged about `1.05x` the best-known upper bound
- `testset_ubo200` 10-instance sample:
  - `4 feasible / 2 infeasible / 4 unknown`
  - exact cases in the sample were solved at `2/2`

This is why the next CP work should target `30s` behavior explicitly, while keeping the short-budget baseline stable.
