# CP Blueprint

This document defines the intended `CP-style` architecture for the custom `RCPSP/max` backend.

It is the implementation contract for [rcpsp/cp/solver.py](rcpsp/cp/solver.py), not a benchmark log. Use [ITERATION_NOTES.md](ITERATION_NOTES.md) for experiments and results.

## Problem model

We model the dataset as `difference constraints` on activity start times:

- `s[i] + c <= s[j]`

This covers both minimum and maximum lags:

- positive `c`: minimum separation
- negative `c`: maximum-lag-style restriction after conversion to the same start-time form

We do **not** build the CP backend around separate `end` variables. Durations only appear when:

- converting a resource order into an added difference constraint
- checking resource overlap
- computing the makespan bound at the sink

## Goal

Build a custom `branch-and-propagate` backend that follows the architecture of proven `RCPSP/max` CP/LCG solvers closely enough to improve quality and classification, without depending on an external solver engine.

## Blueprint

### 1. Time windows

Maintain explicit activity windows:

- `EST[a]`: earliest feasible start
- `LST[a]`: latest feasible start under the incumbent bound

Propagation rules:

- forward tightening from difference constraints and added disjunctive edges
- backward tightening from the incumbent makespan bound
- fail immediately on temporal inconsistency

### 2. Timetable propagation

Use `EST/LST` to build compulsory parts:

- compulsory interval of activity `a` is `[LST[a], EST[a] + dur[a])`
- if this interval is non-empty, the activity must consume resource capacity there

Then:

- detect mandatory overloads
- prune `EST/LST` against the resource timetable
- repeat to a fixpoint with temporal propagation

This is the first real global resource propagator in the backend.

### 3. Overload explanations

When timetable propagation fails on a resource/time window:

- extract the responsible activity set
- keep the explanation object explicit

This explanation should become the driver for:

- branching
- failure caching
- future nogood learning

Status:

- explicit timetable-overload explanations are now implemented
- they are not yet used directly for branching or failure caching

### 4. Conflict-directed branching

Branch on explained overload sets, not arbitrary activity pairs.

Preferred shape:

- identify a resource conflict set
- create children by imposing disjunctive resource orders
- reuse propagated node state when descending

This backend already uses conflict-set branching; the next step is to tie it more directly to timetable explanations.

### 5. Failure cache

Cache failed branches using a compact key over added resource-order decisions.

Purpose:

- avoid rediscovering the same dead subtree
- make restarts worthwhile

Current `seen` handling is only a basic duplicate-state filter. The target is a real failure-oriented cache.

### 6. Restarts with incumbent guidance

The heuristic backend remains the incumbent generator.

The CP backend should:

- use a short heuristic-guided warm-start phase
- spend most of the budget on propagation + search
- prune with the incumbent makespan bound
- benefit from restarts once explanations/failure caching are stronger

## Current implemented subset

Implemented in [rcpsp/cp/solver.py](rcpsp/cp/solver.py):

- difference-constraint forward propagation for `EST`
- incumbent-based backward propagation for `LST`
- conflict-set branching
- timetable / compulsory-part pruning
- explicit timetable-overload explanations
- hybrid-guided warm-start incumbent phase
- basic duplicate-state filtering

Not implemented yet:

- explanation-driven branching
- failure cache / nogood learning beyond the current `seen` set
- stronger cumulative reasoning such as edge-finding or energetic explanations
- restart policy informed by failures

## Development order

Follow this order unless benchmark evidence clearly says otherwise:

1. failure cache keyed by explained conflicts / order sets
2. branching tied to explanations
3. stronger cumulative reasoning
4. restart policy improvements

Do **not** keep adding isolated heuristics unless they fit one of these blueprint steps.

## Guardrails

- Keep the accepted `hybrid` backend stable.
- Use the `cp` backend as the experimental architecture.
- Evaluate every accepted CP iteration with:
  - `benchmark`
  - `compare`
- Prefer changes that improve `sm_j20` and do not obviously hurt broader guardrails.

## References

- [Solving RCPSP/max by lazy clause generation](https://link.springer.com/article/10.1007/s10951-012-0285-x)
- [ptal/kobe-scheduling](https://github.com/ptal/kobe-scheduling)
- [rcpsp/cp/README.md](rcpsp/cp/README.md)
- [ITERATION_NOTES.md](ITERATION_NOTES.md)
