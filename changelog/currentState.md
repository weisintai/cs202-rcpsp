# Current Project State

## Status: Step 8 In Progress — Experiments 1-4 Implemented, Biased Seeding Added, Updated J10/J20 Support Added

## What's Done

- Read and understood problem specification (Project.pdf)
- Analysed input formats: `.sm` (standard PSPLIB) and `.SCH`
- Evaluated 3 algorithm candidates, selected Genetic Algorithm with SSGS decoder
- Evaluated 3 language candidates, selected C++17
- Wrote implementation plan (`implementation.md`) with 7 steps and complexity analysis
- Documented C++ performance strategy (`cpp_performance.md`)
- **Step 1 complete:** Parser handles `.sm` plus both `.SCH` variants used in this repo
  - lag-bearing `.SCH` parser filters out negative time lags (max time lags) to produce a clean DAG
  - compact `.SCH` parser supports the updated local J10/J20 assignment format
  - `.sm` parser reads section headers, precedence, durations, and resource capacities
  - Debug print to stderr, output to stdout
- **Step 2 complete:** SSGS decoder + topological sort + feasibility validator
  - Kahn's algorithm topological sort with cycle-resilient fallback (forces lowest in-degree node when stalled)
  - `remove_back_edges()` cleans up cycle edges from predecessor/successor lists after topo sort
  - SSGS decodes an activity list into a schedule: flat resource profile `usage[t*K + k]`, early-break on resource conflict
  - Makespan is now computed as the true project finish time (`max finish time`) rather than assuming the dummy sink always captures all terminal jobs
  - SSGS now reports impossible single-activity resource demands cleanly instead of crashing
  - `validate()` checks both precedence and resource constraints independently of SSGS
  - Standard `.sm` datasets validate cleanly; the updated local `.SCH` sets contain a small number of infeasible files
- **Refactor:** Split monolithic `solver.cpp` into `src/` with separate files per concern
  - `types.h`, `parser.h/.cpp`, `graph.h/.cpp`, `ssgs.h/.cpp`, `validator.h/.cpp`, `main.cpp`
  - Validated on standard `.sm` datasets plus the updated local `.SCH` sets

- **Step 3 complete:** Priority-rule initial solution generators
  - 4 priority rules: LFT (latest finish time), MTS (most total successors), GRD (greatest resource demand), SPT (shortest processing time)
  - Priority-biased topological sort using min-heap to pick best eligible activity
  - Random feasible permutation generator (random tie-breaking in Kahn's)
  - `generate_initial_solutions()` produces 4 rule-based + N random solutions
  - Main picks best of 24 candidates (4 rules + 20 random), significant makespan improvement
  - Sample: PSP1 J10 went from 33 (plain topo) to 25, PSP2 J10 from 51 to 46
  - Standard `.sm` datasets validate cleanly; updated local `.SCH` datasets include a small number of infeasible input files
  - **Enhancement (weisintai):** Randomized biased seeding — replaces most pure-random initial seeds with LFT/MTS-biased randomized topological sorts. Of 20 random seeds: 10 LFT-biased, 6 MTS-biased, 4 pure random. Uses candidate pool of 3 (sample from top-3 eligible by priority). Motivated by experiment 4 results showing LFT and MTS are the strongest rules.

- **Step 4 complete:** Genetic Algorithm
  - Activity-list representation with SSGS decoder
  - Population size 100, tournament selection (size 5)
  - One-point crossover (preserves precedence feasibility)
  - Two mutation operators: adjacent swap + shift-to-earlier-position
  - Steady-state replacement (replace worst if offspring is better)
  - 28-second time budget, ~8-17M generations on J10-J30
  - Improvements over Step 3: e.g. PSP100 J10: 43→39, PSP1 J20: 50→47
  - All tested feasible instances: 0 violations

- **Step 5 complete:** Forward-backward improvement (double justification)
  - Backward SSGS: schedules activities as late as possible (latest-start times)
  - Forward re-pass: extracts new ordering from backward schedule, re-decodes with forward SSGS
  - Iterates up to 10 times until no improvement
  - Integrated into GA: applied to best individual every 50K generations + final pass
  - All tested feasible instances: 0 violations

## What's Next
- **Step 8:** Run experiments 1-4 (see `experiments.md` for full plan)
  - Experiment 1: Algorithm component ablation
  - Experiment 2: Scaling across instance sizes (partially done — 3s results collected)
  - Experiment 3: Time budget sensitivity
  - Experiment 4: Priority rule comparison
- **Re-benchmark:** Re-run experiments 1-4 with biased seeding to get before/after comparison
- **Report:** Write 6-10 page report using experiment results (35% of grade)
- **Slides:** Create 8-12 slide presentation (25% of grade)

## Key Files

| File | Purpose |
|---|---|
| `implementation.md` | Implementation plan and algorithm spec |
| `cpp_performance.md` | C++ optimisation strategy and rationale |
| `changelog/currentState.md` | This file — tracks where we are |
| `sm_j10/` | J10 benchmark instances (270 `.SCH` files, updated compact RCPSP-style format) |
| `sm_j20/` | J20 benchmark instances (270 `.SCH` files, updated compact RCPSP-style format) |
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
| `reportFormat.md` | Report structure and section breakdown |
| `experiments.md` | Experiment plan with goals, metrics, success criteria |
| `experiments/` | Experiment scripts and results |
| `programFlow.md` | End-to-end walkthrough of how the solver works |

## Experiment 1: Algorithm Component Ablation (5s timeout, --time 3, with biased seeding)

**J30 (480 instances):**

| Config | Optimal | Optimal % | Mean Gap | Mean Quality |
|--------|---------|-----------|----------|--------------|
| Baseline | 153 | 31.9% | 12.46% | 89.85% |
| Priority | 288 | 60.0% | 2.64% | 97.57% |
| GA only | 340 | 70.8% | 1.08% | 98.97% |
| Full | 376 | 78.3% | 0.60% | 99.42% |

**J60 (480 instances):**

| Config | Optimal | Optimal % | Mean Gap | Mean Quality |
|--------|---------|-----------|----------|--------------|
| Baseline | 136 | 28.3% | 15.11% | 88.10% |
| Priority | 300 | 62.5% | 3.89% | 96.57% |
| GA only | 289 | 60.2% | 2.92% | 97.32% |
| Full | 338 | 70.4% | 1.71% | 98.40% |

**Key findings:** Priority rules provide the largest single improvement (~10pp gap reduction). GA adds ~2pp. Forward-backward improvement adds ~0.3-1pp. Biased seeding improved priority mode (J30: 57.7%→60.0%, J60: 59.4%→62.5%) and full pipeline (J30: 0.73%→0.60% gap, J60: 1.92%→1.71% gap).

## Experiment 2: Scaling Across Instance Sizes (5s timeout, --time 3, with biased seeding)

| Dataset | Instances | Optimal | Optimal % | Mean Gap | Max Gap | Mean Quality | Mean Time |
|---------|-----------|---------|-----------|----------|---------|--------------|-----------|
| J30     | 480       | 373     | 77.7%     | 0.60%    | 8.62%   | 99.42%       | 3.01s     |
| J60     | 480       | 338     | 70.4%     | 1.71%    | 14.12%  | 98.40%       | 3.01s     |
| J90     | 480       | 340     | 70.8%     | 2.18%    | 15.65%  | 98.00%       | 3.01s     |
| J120    | 600       | 160     | 26.7%     | 6.06%    | 16.30%  | 94.48%       | 3.01s     |

**Biased seeding impact:** Mean gap improved across all datasets. Biggest gains on J60 (1.91%→1.71%) and J120 (6.25%→6.06%, max gap 20.77%→16.30%).

## Experiment 3: Time Budget Sensitivity (pre-biased seeding)

**J30 (480 instances):**

| GA Time | Optimal | Optimal % | Mean Gap | Max Gap | Mean Quality |
|---------|---------|-----------|----------|---------|--------------|
| 1s      | 362     | 75.4%     | 0.78%    | 10.34%  | 99.25%       |
| 3s      | 362     | 75.4%     | 0.78%    | 10.34%  | 99.26%       |
| 10s     | 362     | 75.4%     | 0.78%    | 10.34%  | 99.26%       |
| 28s     | 362     | 75.4%     | 0.78%    | 10.34%  | 99.26%       |

**J60 (480 instances):**

| GA Time | Optimal | Optimal % | Mean Gap | Max Gap | Mean Quality |
|---------|---------|-----------|----------|---------|--------------|
| 1s      | 333     | 69.4%     | 1.94%    | 13.27%  | 98.20%       |
| 3s      | 333     | 69.4%     | 1.92%    | 12.64%  | 98.22%       |
| 10s     | 334     | 69.6%     | 1.90%    | 12.64%  | 98.24%       |
| 28s     | 335     | 69.8%     | 1.89%    | 12.64%  | 98.24%       |

**Key findings:** J30 saturates at 1s — GA converges fully within 1s. J60 shows marginal improvement with more time (1.94% → 1.89% gap from 1s to 28s).

## Experiment 4: Priority Rule Comparison (pre-biased seeding)

**J30 (480 instances):**

| Rule   | Optimal | Optimal % | Mean Gap | Max Gap | Mean Quality | Times Best |
|--------|---------|-----------|----------|---------|--------------|------------|
| RANDOM | 154     | 32.1%     | 13.56%   | 60.47%  | 89.10%       | 170        |
| LFT    | 238     | 49.6%     | 5.39%    | 33.85%  | 95.29%       | 366        |
| MTS    | 202     | 42.1%     | 6.87%    | 38.18%  | 94.05%       | 279        |
| GRD    | 158     | 32.9%     | 11.67%   | 51.11%  | 90.42%       | 191        |
| SPT    | 137     | 28.5%     | 17.63%   | 65.52%  | 86.47%       | 143        |

**J60 (480 instances):**

| Rule   | Optimal | Optimal % | Mean Gap | Max Gap | Mean Quality | Times Best |
|--------|---------|-----------|----------|---------|--------------|------------|
| RANDOM | 141     | 29.4%     | 15.77%   | 63.86%  | 87.73%       | 149        |
| LFT    | 271     | 56.5%     | 5.68%    | 33.33%  | 95.16%       | 403        |
| MTS    | 224     | 46.7%     | 7.11%    | 33.00%  | 93.96%       | 301        |
| GRD    | 139     | 29.0%     | 15.05%   | 54.17%  | 88.11%       | 142        |
| SPT    | 125     | 26.0%     | 19.99%   | 78.12%  | 85.16%       | 125        |

**Key findings:** LFT is the strongest rule overall (best in 366/480 J30, 403/480 J60). MTS is second. GRD and SPT perform close to or worse than random. This motivated the biased seeding enhancement.

## Latest Benchmark Results (3s safety sweep, biased seeding)

The final `3s` safety sweep confirmed that the parser and makespan fixes do not change the main PSPLIB benchmark results.

| Dataset | Instances | Valid | Best-known Matches | Match % | Mean Gap | Max Gap | Mean Quality |
|---------|-----------|-------|--------------------|---------|----------|---------|--------------|
| J30     | 480       | 480   | 373                | 77.7%   | 0.67%    | 8.16%   | 99.35%       |
| J60     | 480       | 480   | 334                | 69.6%   | 1.73%    | 11.36%  | 98.39%       |
| J90     | 480       | 480   | 345                | 71.9%   | 2.08%    | 13.01%  | 98.09%       |
| J120    | 600       | 600   | 161                | 26.8%   | 6.04%    | 21.43%  | 94.49%       |

Representative outputs are written under:
- `benchmark_results/safety_3s/j30/`
- `benchmark_results/safety_3s/j60/`
- `benchmark_results/safety_3s/j90/`
- `benchmark_results/safety_3s/j120/`

## Updated Local J10/J20 Benchmark Status (5s timeout, --time 3, full pipeline)

The instructor-updated local J10/J20 `.SCH` files now use a compact RCPSP-style format rather than the earlier lag-bearing assumption. A subset of them is infeasible as provided because at least one activity demand exceeds the declared capacity; the benchmark harness now records these cases as `infeasible_input`.

| Dataset | Instances | OK | Infeasible Input Files | Timeouts |
|---------|-----------|----|------------------------|----------|
| J10     | 270       | 253 | 17 | 0 |
| J20     | 270       | 266 | 4  | 0 |

Representative outputs are written under:
- `benchmark_results/j10_updated_3s/`
- `benchmark_results/j20_updated_3s/`

## Open Issues

- **Cycle detection (partially resolved):** The lag-bearing `.SCH` parser filters out negative-lag edges, and the topological sort now has a cycle-resilient fallback that breaks remaining cycles. `remove_back_edges()` cleans up the graph afterwards. However, there is no user-facing warning when cycles are detected and broken — consider adding a stderr warning. Does not affect `.sm` files (DAGs by definition).
- **Updated J10/J20 data quality:** 17 J10 files and 4 J20 files are infeasible as provided because an activity's demand exceeds the declared capacity. These are now reported cleanly as input errors rather than causing a crash.

## Decisions Log

| Decision | Rationale |
|---|---|
| GA with SSGS decoder | Best-studied metaheuristic for RCPSP; anytime property; natural constraint handling |
| C++17 | ~200-500x more schedule evaluations than Python in 30s; true multithreading |
| 28s time budget (2s margin) | Ensures output before the 30s hard cutoff |
| Biased seeding (LFT/MTS) | Experiment 4 showed LFT and MTS dominate other rules; concentrate initial population near strong heuristic regions |
