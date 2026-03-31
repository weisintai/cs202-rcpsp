# Current Project State

## Status: Step 1 Complete — Parser Done

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

## What's Next

- **Step 2:** Implement Serial Schedule Generation Scheme (SSGS)
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

- **Cycle detection:** The `.SCH` parser prevents cycles by filtering out negative-lag edges, but there is no explicit cycle detection (e.g. topological sort failure check) as a safety net for malformed input. Consider adding an O(n + E) check before scheduling. Does not affect `.sm` files (DAGs by definition).

## Decisions Log

| Decision | Rationale |
|---|---|
| GA with SSGS decoder | Best-studied metaheuristic for RCPSP; anytime property; natural constraint handling |
| C++17 | ~200-500x more schedule evaluations than Python in 30s; true multithreading |
| 28s time budget (2s margin) | Ensures output before the 30s hard cutoff |
