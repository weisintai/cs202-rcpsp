# Current Project State

## Status: Step 2 Complete — SSGS Working

## What's Done

- Read and understood problem specification (Project.pdf)
- Analysed input formats: `.sm` (standard PSPLIB) and `.SCH` (ProGenMax)
- Evaluated 3 algorithm candidates, selected Genetic Algorithm with SSGS decoder
- Evaluated 3 language candidates, selected C++17
- Wrote implementation plan (`implementation.md`) with 7 steps and complexity analysis
- Documented C++ performance strategy (`cpp_performance.md`)
- **Step 1 complete:** Parser handles both `.sm` and `.SCH` formats, tested on all 540 instances
  - `.SCH` parser filters out negative time lags (max time lags) to produce a clean DAG
  - `.sm` parser reads section headers, precedence, durations, and resource capacities
  - Debug print to stderr, output to stdout
- **Step 2 complete:** SSGS decoder + topological sort + feasibility validator
  - Kahn's algorithm topological sort with cycle-resilient fallback (forces lowest in-degree node when stalled)
  - `remove_back_edges()` cleans up cycle edges from predecessor/successor lists after topo sort
  - SSGS decodes an activity list into a schedule: flat resource profile `usage[t*K + k]`, early-break on resource conflict
  - `validate()` checks both precedence and resource constraints independently of SSGS
  - All 540 instances produce feasible schedules (0 violations)

## What's Next

- **Step 3:** Implement priority-rule initial solution generators
- **Step 3:** Implement priority-rule initial solution generators
- **Step 4:** Implement Genetic Algorithm (selection, crossover, mutation, replacement)
- **Step 5:** Implement forward-backward improvement
- **Step 6:** Output formatting and feasibility validation
- **Step 7:** Test on J10/J20 benchmarks and compare against known optima

## Key Files

| File | Purpose |
|---|---|
| `implementation.md` | Implementation plan and algorithm spec |
| `cpp_performance.md` | C++ optimisation strategy and rationale |
| `changelog/currentState.md` | This file — tracks where we are |
| `sm_j10/` | J10 benchmark instances (270 files) |
| `sm_j20/` | J20 benchmark instances (270 files) |
| `solver.cpp` | Main solver source (single-file) |
| `Makefile` | Build config: `make` for optimised, `make debug` for sanitizer |

## Open Issues

- **Cycle detection (partially resolved):** The `.SCH` parser filters out negative-lag edges, and the topological sort now has a cycle-resilient fallback that breaks remaining cycles. `remove_back_edges()` cleans up the graph afterwards. This handles all 540 test instances. However, there is no user-facing warning when cycles are detected and broken — consider adding a stderr warning. Does not affect `.sm` files (DAGs by definition).

## Decisions Log

| Decision | Rationale |
|---|---|
| GA with SSGS decoder | Best-studied metaheuristic for RCPSP; anytime property; natural constraint handling |
| C++17 | ~200-500x more schedule evaluations than Python in 30s; true multithreading |
| 28s time budget (2s margin) | Ensures output before the 30s hard cutoff |
