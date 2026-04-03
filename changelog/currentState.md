# Current Project State

## Status: Implementation Complete; Report Prep and Documentation Cleanup

## What's Done

- Read and understood problem specification (Project.pdf)
- Analysed input formats: `.sm` (standard PSPLIB) and `.SCH`
- Evaluated 3 algorithm candidates, selected Genetic Algorithm with SSGS decoder
- Evaluated 3 language candidates, selected C++17
- Wrote implementation notes (`implementation.md`) with 8 steps and complexity analysis
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
  - Mutation neighborhood now includes adjacent swap, non-adjacent feasible swap, and bidirectional insertion within precedence-feasible bounds
  - Steady-state replacement (replace worst if offspring is better)
  - 28-second time budget, ~8-17M generations on J10-J30
  - Improvements over Step 3: e.g. PSP100 J10: 43→39, PSP1 J20: 50→47
  - All tested feasible instances: 0 violations
  - **Enhancement (weisintai):** Optional schedule-budget stopping rule via `--schedules <count>` for internal A/B experiments. This counts `SSGS` schedule generations in the GA so algorithm comparisons are less tied to raw machine speed.
  - **Enhancement (weisintai):** Restart-on-stagnation diversification. After long stagnation, the GA keeps a small elite set and refreshes the rest of the population with fresh guided/random seeds.
  - **Tuning (weisintai):** Restart stagnation threshold tuned from `200k` to `100k` generations. The `100k` setting improved the J90 regression subset under the `1m` schedule-budget protocol and also improved aggregate `3s` wall-clock results on J30, J60, J90, and J120.
  - **Enhancement (weisintai):** Duplicate-aware diversity control. The initial population and restart refills are kept mostly unique, and exact-duplicate offspring are rejected unless a few extra perturbation attempts produce a distinct activity list.

- **Step 5 complete:** Forward-backward improvement (double justification)
  - Backward SSGS: schedules activities as late as possible (latest-start times)
  - Forward re-pass: extracts new ordering from backward schedule, re-decodes with forward SSGS
  - Iterates up to 10 times until no improvement
  - Integrated into GA: applied to best individual every 50K generations + final pass
  - All tested feasible instances: 0 violations

- **Performance refinements kept:**
  - precompute the safe scheduling horizon once during parsing and reuse it in every `SSGS` decode
  - move impossible single-activity resource-demand checks from the `SSGS` hot loop to parse time
  - replace string-based duplicate keys with compact 64-bit fingerprints
  - these optimisations improved the diversity-control `J90` schedule-budget run by roughly `20%` to `25%` wall-clock while preserving the same strong quality pattern

## What's Next
- Freeze the current default solver line unless a clearly better schedule-budget result survives a sequential `3s` rerun.
- Consolidate report-ready figures and tables around the canonical benchmark artifacts in `benchmark_results/`.
- Keep the report framing honest: Experiments 1-4 justify the architecture, scaling, anytime behavior, and heuristic choices, while the later solver refinements are captured by the benchmark history under `benchmark_results/`.
- Use sequential wall-clock reruns for any final report-facing benchmark refresh to reduce CPU-contention noise from parallel wrappers.
- Write the report and slide deck.

## Key Files

| File | Purpose |
|---|---|
| `implementation.md` | Implementation notes and algorithm spec |
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

## Experiment 1: Algorithm Component Ablation (5s timeout, --time 3, sequential rerun)

**J30 (480 instances):**

| Config | Optimal | Optimal % | Mean Gap | Mean Quality |
|--------|---------|-----------|----------|--------------|
| Baseline | 154 | 32.1% | 13.56% | 89.10% |
| Priority | 289 | 60.2% | 2.63% | 97.57% |
| GA only | 430 | 89.6% | 0.21% | 99.79% |
| Full | 428 | 89.2% | 0.23% | 99.78% |

**J60 (480 instances):**

| Config | Optimal | Optimal % | Mean Gap | Mean Quality |
|--------|---------|-----------|----------|--------------|
| Baseline | 141 | 29.4% | 15.77% | 87.73% |
| Priority | 304 | 63.3% | 3.93% | 96.54% |
| GA only | 351 | 73.1% | 1.42% | 98.66% |
| Full | 351 | 73.1% | 1.26% | 98.81% |

**Key findings:** Priority rules still provide the largest jump over the random baseline, and GA adds the dominant additional improvement. The forward-backward layer is now a modest refinement rather than a dramatic jump: on this rerun it helped clearly on J60 by mean gap, while J30 was essentially tied and GA-only slightly edged full by raw best-known matches.

## Experiment 2: Scaling Across Instance Sizes (5s timeout, --time 3, sequential rerun)

| Dataset | Instances | Optimal | Optimal % | Mean Gap | Max Gap | Mean Quality | Mean Time |
|---------|-----------|---------|-----------|----------|---------|--------------|-----------|
| J30     | 480       | 427     | 89.0%     | 0.24%    | 6.78%   | 99.76%       | 3.01s     |
| J60     | 480       | 351     | 73.1%     | 1.27%    | 11.58%  | 98.80%       | 3.00s     |
| J90     | 480       | 350     | 72.9%     | 1.79%    | 11.76%  | 98.34%       | 3.00s     |
| J120    | 600       | 167     | 27.8%     | 5.38%    | 15.20%  | 95.06%       | 3.01s     |

**Scaling takeaway:** The current full solver remains strong on J30 through J90 and degrades mainly at J120, which is the expected scaling story to use in the report.

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

## Latest Benchmark Results (Current 3s Solver)

The current best solver line combines biased seeding, the stronger mutation neighborhood, restart-on-stagnation at `100k`, duplicate-aware diversity control, and the recent hot-path optimisations.

| Dataset | Instances | Best-known Matches | Match % | Mean Gap |
|---------|-----------|--------------------|---------|----------|
| J30     | 480       | 427                | 89.0%   | 0.2394%  |
| J60     | 480       | 351                | 73.1%   | 1.2718%  |
| J90     | 480       | 350                | 72.9%   | 1.7914%  |
| J120    | 600       | 167                | 27.8%   | 5.3772%  |

Representative outputs are written under:
- `benchmark_results/restart_tuning_3s/j30/`
- `benchmark_results/restart_tuning_3s/j60/`
- `benchmark_results/restart_tuning_3s/j90/`
- `benchmark_results/restart_tuning_3s/j120/`

Treat these `benchmark_results/restart_tuning_3s/` folders as the canonical current-best `3s` artifacts. The rerunnable `experiments/*/results/` folders are working outputs and may be overwritten by later benchmark runs.

## Historical Experiment Snapshots

The experiment sections below are retained as design-history snapshots and report notes. They are useful for explaining why the solver changed, but they should not be mistaken for the canonical current-best benchmark record above.

In the report, these experiment snapshots should be paired with a short refinement-history summary so the later gains from stronger mutation, restart tuning, duplicate-aware diversity control, and hot-path optimisation are not lost.

## Restart-On-Stagnation Benchmark Results

The restart-on-stagnation change was first checked under the schedule-budget protocol, then confirmed under the normal `3s` wall-clock benchmark.

### Schedule-budget checks

- **J90 regression subset (55 instances, 1,000,000 schedules):**
  - improved vs GA `1m` baseline: `10/55`
  - worse vs GA `1m` baseline: `1/55`
  - recovered to old baseline-or-better: `5/55`

- **J60 full (480 instances, 1,000,000 schedules):**
  - improved vs GA `1m` baseline: `30/480`
  - matched baseline: `438/480`
  - worse than baseline: `12/480`

### 3-second wall-clock comparison vs neighborhood-upgrade baseline

| Dataset | Best-known matches | Mean gap | Max gap | Interpretation |
|---------|--------------------|----------|---------|----------------|
| J30 | `391 → 405` | `0.5071% → 0.3576%` | `6.90% → 6.78%` | clear improvement |
| J60 | `341 → 342` | `1.5941% → 1.5077%` | `11.24% → 10.53%` | improvement |
| J90 | `342 → 342` | `2.1246% → 2.0838%` | `15.75% → 14.96%` | slight recovery |
| J120 | `162 → 161` | `5.8255% → 5.8226%` | `16.56% → 17.58%` | roughly neutral |

## Restart Threshold Tuning (`100k` vs `200k` vs `300k`)

The initial restart version used a stagnation threshold of `200k` generations. We then tuned this under the schedule-budget protocol and confirmed the best candidate with a normal `3s` wall-clock sweep.

### J90 regression subset (55 instances, 1,000,000 schedules)

- `100k`: improved vs GA `1m` on `17/55`, recovered to old baseline-or-better on `8/55`
- `200k`: improved vs GA `1m` on `10/55`, recovered on `5/55`
- `300k`: improved vs GA `1m` on `9/55`, recovered on `6/55`

### J60 full (480 instances, 1,000,000 schedules)

- `100k` vs old `1m` schedule-budget reference:
  - improved: `48/480`
  - matched: `424/480`
  - worse: `8/480`
  - best-known matches: `341 → 346`
  - mean gap: `1.5982% → 1.4212%`

### 3-second wall-clock comparison (`100k` vs `200k`)

| Dataset | Best-known matches | Mean gap | Interpretation |
|---------|--------------------|----------|----------------|
| J30 | `405 → 418` | `0.3576% → 0.2883%` | clear improvement |
| J60 | `342 → 346` | `1.5077% → 1.4262%` | improvement |
| J90 | `342 → 345` | `2.0838% → 2.0458%` | improvement |
| J120 | `161 → 164` | `5.8226% → 5.7153%` | improvement |

This made `100k` the new default restart threshold.

## Duplicate-Aware Diversity Control Results

After restart tuning, we added a duplicate-aware population filter and then reduced its overhead with two hot-path optimisations.

### Schedule-budget checks

- **J90 regression subset (55 instances, 1,000,000 schedules):**
  - improved vs GA `1m`: `48/55`
  - matched GA `1m`: `5/55`
  - worse vs GA `1m`: `2/55`
  - recovered to baseline-or-better: `35/55`

- **J60 full (480 instances, 1,000,000 schedules):**
  - improved vs reference: `78/480`
  - matched reference: `376/480`
  - worse than reference: `26/480`
  - best-known matches: `346 → 350`
  - mean gap: `1.4212% → 1.2811%`

### 3-second wall-clock comparison vs restart-only baseline

| Dataset | Best-known matches | Mean gap |
|---------|--------------------|----------|
| J30 | `405 → 427` | `0.3576% → 0.2394%` |
| J60 | `342 → 351` | `1.5077% → 1.2718%` |
| J90 | `342 → 350` | `2.0838% → 1.7914%` |
| J120 | `161 → 167` | `5.8226% → 5.3772%` |

This is the strongest solver line so far and is the current default.

This is the first post-neighborhood refinement that remained positive under both schedule-budget and wall-clock benchmarking, so it is the current solver line to keep.

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
- **Experimental protocol is still mostly wall-clock based:** This is fine for the final project requirement, but weak for internal algorithm comparison. The RCPSP literature commonly also uses fixed schedule-generation limits and several independent runs for randomized methods. See `changelog/solverImprovementIdeas.md`.

## Decisions Log

| Decision | Rationale |
|---|---|
| GA with SSGS decoder | Best-studied metaheuristic for RCPSP; anytime property; natural constraint handling |
| C++17 | ~200-500x more schedule evaluations than Python in 30s; true multithreading |
| 28s time budget (2s margin) | Ensures output before the 30s hard cutoff |
| Biased seeding (LFT/MTS) | Experiment 4 showed LFT and MTS dominate other rules; concentrate initial population near strong heuristic regions |
| Keep wall-clock for report, add schedule-budget for internal A/B tests | Separates search quality from implementation speed; aligns better with RCPSP benchmark protocol literature |
