# CP Backend

This is the current submission-oriented `CP-style` backend.

The implementation roadmap for this backend lives in [../../CP_ROADMAP.md](../../CP_ROADMAP.md).

## Purpose

- provide a separate branch-and-propagate architecture
- make stronger scheduling-CP changes without destabilizing the comparison backends

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

The core modeling direction is standard for `RCPSP/max`: temporal lag closure, cumulative-capacity pruning, search over resource-order decisions, and branch-and-bound against an incumbent makespan. Changes here should target `stronger propagation and branching`, not generic heuristic polishing.

## What Stronger CP Still Means Here

This backend is still lighter than a strong external scheduling CP solver. The main missing pieces are:

- timetable-edge-finding or similarly strong cumulative propagation
- richer `not-first / not-last` inference
- smaller reusable overload explanations and failure cores
- more incremental propagation scheduling instead of mostly recompute-to-fixpoint
- stronger incumbent generation on hard feasible cases

Those are the gaps that still separate this backend from stronger scheduling CP implementations in the literature and in industrial solvers.

## Current Direction

This backend is now following a stricter route:

- stay self-contained inside `rcpsp/cp`
- use `guided_seed` only as a local incumbent/proof helper
- improve the backend through stronger propagation, explanations, and branching
- screen changes first on `submission_quick` and `broad_generalization`
- only call a change submission-ready after the `cp_acceptance` and `submission` presets from [../../CP_ROADMAP.md](../../CP_ROADMAP.md)

## Practical Read

The important operational split is now:

- `0.1s` and `1.0s` guardrails protect the short-budget submission path
- `30s` runs are where deeper-budget CP ideas should be tested
- any heavier propagation or search policy should be explicitly budget-gated

This backend is not trying to clone CP-SAT or CP Optimizer. The goal is a strong scheduling-specific CP backend that stays small enough for this repo and this assignment.
