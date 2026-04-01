# Current Project State

## Status: Step 8 In Progress — Experiment 1 (Ablation) Complete

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
- **Refactor:** Split monolithic `solver.cpp` into `src/` with separate files per concern
  - `types.h`, `parser.h/.cpp`, `graph.h/.cpp`, `ssgs.h/.cpp`, `validator.h/.cpp`, `main.cpp`
  - Validated: all 540 .SCH + 480 J30 .sm instances pass (0 violations)

- **Step 3 complete:** Priority-rule initial solution generators
  - 4 priority rules: LFT (latest finish time), MTS (most total successors), GRD (greatest resource demand), SPT (shortest processing time)
  - Priority-biased topological sort using min-heap to pick best eligible activity
  - Random feasible permutation generator (random tie-breaking in Kahn's)
  - `generate_initial_solutions()` produces 4 rule-based + N random solutions
  - Main picks best of 24 candidates (4 rules + 20 random), significant makespan improvement
  - Sample: PSP1 J10 went from 33 (plain topo) to 25, PSP2 J10 from 51 to 46
  - All 540 .SCH + 480 J30 .sm instances: 0 violations

- **Step 4 complete:** Genetic Algorithm
  - Activity-list representation with SSGS decoder
  - Population size 100, tournament selection (size 5)
  - One-point crossover (preserves precedence feasibility)
  - Two mutation operators: adjacent swap + shift-to-earlier-position
  - Steady-state replacement (replace worst if offspring is better)
  - 28-second time budget, ~8-17M generations on J10-J30
  - Improvements over Step 3: e.g. PSP100 J10: 43→39, PSP1 J20: 50→47
  - All tested instances: 0 violations

- **Step 5 complete:** Forward-backward improvement (double justification)
  - Backward SSGS: schedules activities as late as possible (latest-start times)
  - Forward re-pass: extracts new ordering from backward schedule, re-decodes with forward SSGS
  - Iterates up to 10 times until no improvement
  - Integrated into GA: applied to best individual every 50K generations + final pass
  - All tested instances: 0 violations

## What's Next
- **Step 8:** Run experiments 1-4 (see `experiments.md` for full plan)
  - Experiment 1: Algorithm component ablation
  - Experiment 2: Scaling across instance sizes (partially done — 3s results collected)
  - Experiment 3: Time budget sensitivity
  - Experiment 4: Priority rule comparison
- **Report:** Write 6-10 page report using experiment results (35% of grade)
- **Slides:** Create 8-12 slide presentation (25% of grade)
- **README:** Write README with run command

## Key Files

| File | Purpose |
|---|---|
| `implementation.md` | Implementation plan and algorithm spec |
| `cpp_performance.md` | C++ optimisation strategy and rationale |
| `changelog/currentState.md` | This file — tracks where we are |
| `sm_j10/` | J10 benchmark instances (270 .SCH files, ProGenMax format) |
| `sm_j20/` | J20 benchmark instances (270 .SCH files, ProGenMax format) |
| `datasets/psplib/j30/instances/` | J30 benchmark instances (480 .sm files) |
| `datasets/psplib/j60/instances/` | J60 benchmark instances (480 .sm files) |
| `datasets/psplib/j90/instances/` | J90 benchmark instances (480 .sm files) |
| `datasets/psplib/j120/instances/` | J120 benchmark instances (600 .sm files) |
| `scripts/benchmark_rcpsp.py` | Benchmarking script (invoked via `make bench-*`) |
| `src/types.h` | Problem and Schedule structs |
| `src/parser.h/.cpp` | Format detection + .sm and .SCH parsers |
| `src/graph.h/.cpp` | Topological sort + cycle-breaking cleanup |
| `src/ssgs.h/.cpp` | Serial Schedule Generation Scheme decoder |
| `src/validator.h/.cpp` | Feasibility checker (precedence + resource) |
| `src/priority.h/.cpp` | Priority rules (LFT, MTS, GRD, SPT) + random permutations |
| `src/ga.h/.cpp` | Genetic algorithm (selection, crossover, mutation, replacement) |
| `src/improvement.h/.cpp` | Forward-backward improvement (double justification) |
| `src/main.cpp` | Entry point |
| `Makefile` | Build config: `make` for optimised, `make debug` for sanitizer |
| `experiments.md` | Experiment plan with goals, metrics, success criteria |
| `experiments/` | Experiment scripts and results |
| `programFlow.md` | End-to-end walkthrough of how the solver works |

## Experiment 1: Algorithm Component Ablation (5s timeout, --time 3)

**J30 (480 instances):**

| Config | Optimal | Optimal % | Mean Gap | Mean Quality |
|--------|---------|-----------|----------|--------------|
| Baseline | 153 | 31.9% | 12.46% | 89.85% |
| Priority | 277 | 57.7% | 3.03% | 97.24% |
| GA only | 342 | 71.2% | 1.06% | 98.99% |
| Full | 373 | 77.7% | 0.73% | 99.30% |

**J60 (480 instances):**

| Config | Optimal | Optimal % | Mean Gap | Mean Quality |
|--------|---------|-----------|----------|--------------|
| Baseline | 136 | 28.3% | 15.11% | 88.10% |
| Priority | 285 | 59.4% | 4.73% | 95.89% |
| GA only | 289 | 60.2% | 2.91% | 97.33% |
| Full | 329 | 68.5% | 1.92% | 98.22% |

**Key findings:** Priority rules provide the largest single improvement (~10pp gap reduction). GA adds ~2pp. Forward-backward improvement adds ~0.3-1pp.

## Benchmark Results (5s timeout, --time 3)

All instances produce feasible schedules (0 violations across all datasets).

| Dataset | Instances | Valid | Optimal | Optimal % | Mean Gap | Max Gap | Mean Quality |
|---------|-----------|-------|---------|-----------|----------|---------|--------------|
| J30     | 480       | 480   | 374     | 77.9%     | 0.72%    | 9.52%   | 99.31%       |
| J60     | 480       | 480   | 329     | 68.5%     | 1.91%    | 15.28%  | 98.22%       |
| J90     | 480       | 480   | 339     | 70.6%     | 2.20%    | 15.53%  | 97.98%       |
| J120    | 600       | 600   | 158     | 26.3%     | 6.25%    | 20.77%  | 94.32%       |

**Notes:**
- Solver uses `--time 3` (3s GA budget) within a 5s wall-clock timeout
- "Optimal" means matching the best known solution from PSPLIB
- Mean gap = average percentage above best known makespan
- Quality degrades gracefully with instance size, as expected for GA on NP-hard problems

## Open Issues

- **Cycle detection (partially resolved):** The `.SCH` parser filters out negative-lag edges, and the topological sort now has a cycle-resilient fallback that breaks remaining cycles. `remove_back_edges()` cleans up the graph afterwards. This handles all 540 test instances. However, there is no user-facing warning when cycles are detected and broken — consider adding a stderr warning. Does not affect `.sm` files (DAGs by definition).

## Decisions Log

| Decision | Rationale |
|---|---|
| GA with SSGS decoder | Best-studied metaheuristic for RCPSP; anytime property; natural constraint handling |
| C++17 | ~200-500x more schedule evaluations than Python in 30s; true multithreading |
| 28s time budget (2s margin) | Ensures output before the 30s hard cutoff |
