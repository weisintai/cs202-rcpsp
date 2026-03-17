# RCPSP/max Solver

Python-first heuristic solver for the project scheduling instances in this folder.

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

Benchmark a full folder:

```bash
uv run main.py benchmark sm_j10 --time-limit 0.1 --output sm_j10_results.json
```

`benchmark` now prints live progress to `stderr` by default. Use `--no-progress` if you want only the final summary:

```bash
uv run main.py benchmark sm_j10 --time-limit 0.1 --output sm_j10_results.json --no-progress
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
