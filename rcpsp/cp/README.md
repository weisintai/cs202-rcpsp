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

## One-Line Mental Model

The solver does not search directly over full schedules. It searches over extra pairwise resource-order decisions, keeps tightening time windows with propagation, and uses an incumbent makespan to cut away weak branches.

## How A Solve Runs

The easiest way to follow the backend is to read it in this order:

1. `solver.py`
   - thin entrypoint that forwards into `search.py`
2. `search.py`
   - builds the root CP state
   - runs `guided_seed` to try to get an early incumbent
   - runs a bounded pre-incumbent probe if `guided_seed` still leaves CP empty-handed
   - runs DFS over pair-order decisions
   - updates the incumbent when a feasible leaf schedule is found
3. `propagation.py`
   - tightens EST/LST windows
   - runs compulsory-part / timetable pruning
   - infers forced pair orders from time windows
   - detects overload-based conflicts for branching
4. `construct.py`
   - tries to build a feasible warm-start schedule from the current CP state
5. `guided_seed.py`
   - orchestrates the early construct / improve / polish budget before the main DFS
6. `exact.py`
   - legacy exact helper kept for comparison experiments

The normal execution flow is:

1. Parse the instance and compute lag closure.
2. Build the root node with temporal lower bounds and any forced resource orders.
3. Run `guided_seed` to try to get a first incumbent quickly.
4. If that still leaves no incumbent, run a bounded pre-incumbent beam over shallow CP nodes.
5. Enter DFS over pair-order decisions.
6. At each node, propagate temporal and resource constraints to a fixpoint.
7. If propagation proves the node impossible, prune it.
8. If the node yields a valid schedule, compress it and compare it against the incumbent.
9. Otherwise branch on a conflict and recurse until the deadline or proof.

## What Each File Owns

- `search.py`
  - top-level control flow, branching, incumbent handling, diagnostics
- `propagation.py`
  - the main CP reasoning kernel
- `state.py`
  - node/search stats structures that carry CP state through DFS
- `construct.py`
  - CP-native schedule construction attempts for no-incumbent states
- `guided_seed.py`
  - pre-DFS budget split for construct, improve, and polish work
- `exact.py`
  - legacy exact helper kept for comparison experiments

## Where To Work First

If a teammate wants to improve the solver, start here:

- `search.py`
  - for branching policy, budget gating, and incumbent handling
- `propagation.py`
  - for stronger pruning and better explanations
- `construct.py`
  - for first-incumbent generation on hard feasible cases
- `guided_seed.py`
  - for seed-budget allocation and early warm-start behavior
- `scripts/run_cp_residue.py`
  - for the fastest regression loop on the hardest public `30s` misses

In practice, the biggest current weakness is first-incumbent generation on the hardest feasible cases. That means `construct.py` and `guided_seed.py` matter more right now than adding another generic heuristic elsewhere.

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
- a bounded pre-incumbent probe that reuses shallow propagated CP nodes before the main DFS

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
- use `guided_seed` only as a local incumbent helper
- improve the backend through stronger propagation, explanations, and branching
- screen changes first on `submission_quick` and `broad_generalization`
- only call a change submission-ready after the `cp_acceptance` and `submission` presets from [../../CP_ROADMAP.md](../../CP_ROADMAP.md)

The repo still contains `hybrid` and `sgs`, but they are no longer the main path. Use them only when you need a historical comparison or want to borrow a generic idea into `cp` without importing their backend code.

## Practical Read

The important operational split is now:

- `0.1s` and `1.0s` guardrails protect the short-budget submission path
- `30s` runs are where deeper-budget CP ideas should be tested
- any heavier propagation or search policy should be explicitly budget-gated

Recommended daily iteration loop:

1. `uv run python scripts/run_cp_residue.py`
2. `uv run python scripts/run_guardrails.py --preset submission_quick`
3. `uv run python scripts/run_guardrails.py --preset broad_generalization`
4. `uv run python scripts/run_guardrails.py --preset cp_acceptance`

This backend is not trying to clone CP-SAT or CP Optimizer. The goal is a strong scheduling-specific CP backend that stays small enough for this repo and this assignment.
