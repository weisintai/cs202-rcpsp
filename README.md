# RCPSP/max Solver

Python-first heuristic solver for the project scheduling instances in this folder.

## Project layout

- [rcpsp/README.md](rcpsp/README.md)
  - package index and shared module layout
- [rcpsp/heuristic/README.md](rcpsp/heuristic/README.md)
  - accepted main backend
- [rcpsp/cp/README.md](rcpsp/cp/README.md)
  - experimental CP-style backend
- [references/README.md](references/README.md)
  - external reference repos cloned for study

## What it does

- Parses ProGenMax `.SCH` files across the benchmark folders in this repo, including `sm_j10`, `sm_j20`, `sm_j30`, `testset_ubo20`, and `testset_ubo50`
- Handles generalized lag constraints of the form `S_j >= S_i + lag`
- Builds a fast incumbent with a conflict-repair heuristic
- Improves or proves more cases with conflict-set branch-and-bound
- Benchmarks folders of instances from the command line
- Compares benchmark outputs against published reference values for `sm_j10`, `sm_j20`, `sm_j30`, `testset_ubo20`, and `testset_ubo50`
- Reports `feasible`, `infeasible`, or `unknown` per instance

## Usage

Solve one instance:

```bash
uv run main.py solve sm_j10/PSP1.SCH --time-limit 1.0
```

You can switch solver backends explicitly:

```bash
uv run main.py solve sm_j10/PSP1.SCH --time-limit 1.0 --backend hybrid
uv run main.py solve sm_j10/PSP1.SCH --time-limit 1.0 --backend cp
```

Benchmark a full folder:

```bash
uv run main.py benchmark sm_j10 --time-limit 0.1 --output sm_j10_results.json
```

`benchmark` now prints live progress to `stderr` by default. Use `--no-progress` if you want only the final summary:

```bash
uv run main.py benchmark sm_j10 --time-limit 0.1 --output sm_j10_results.json --no-progress
uv run main.py benchmark sm_j10 --time-limit 0.1 --backend cp --output sm_j10_cp.json --no-progress
```

Compare a benchmark JSON against the public reference values:

```bash
uv run main.py compare sm_j20_results_current_clean_1p0.json --dataset sm_j20
```

`compare` also shows live progress by default and supports `--no-progress`.

Supported datasets for `compare` are:

- `sm_j10`
- `sm_j20`
- `sm_j30`
- `testset_ubo20`
- `testset_ubo50`

The benchmark command prints aggregate metrics and optionally writes per-instance results to JSON.

## Reading the benchmark JSON

The per-instance rows contain:

- `status`
  - `feasible`: valid schedule found
  - `infeasible`: current solver exhausted its search without finding a schedule
  - `unknown`: time limit hit before the solver could classify the case
- `makespan`
  - final project completion time of the returned schedule
- `temporal_lower_bound`
  - lower bound from the lag constraints alone, ignoring resource conflicts
- `ratio`
  - `makespan / temporal_lower_bound`
  - lower is better
  - `1.0` means the schedule matches the temporal lower bound
- `runtime_seconds`
  - wall-clock runtime for that instance

For whole-benchmark comparisons, the most useful summary fields are:

1. `feasible`
2. `unknown`
3. `avg_ratio`
4. `avg_runtime_seconds`

When two solver versions solve different sets of instances, compare `avg_ratio` on the common feasible set as well, not only on all feasible instances.

## Research-Inspired Next Steps

These are the smaller CP-style ideas that still fit the current project scope and codebase:

- stronger `mandatory-overlap clique` pruning instead of only pairwise overlap checks
- light `energetic / window-based` resource pruning for obvious overload windows
- better exact-search branching using conflict history or activity failure counts
- stronger incumbent improvement around critical-chain and bottleneck-resource activities
- richer local moves such as pair reinsertion / swap near hard conflicts

What we are deliberately not trying to build from scratch right now:

- a full `lazy clause generation` engine
- a full `global cumulative` propagator
- a full external-solver-grade CP / MIP engine

Those are valid research directions, but they are much larger engineering projects than this assignment needs.

## References

Public solver and model references cloned for local study live in [references/README.md](references/README.md).
