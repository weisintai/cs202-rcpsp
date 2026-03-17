# RCPSP/max Solver

Python-first heuristic solver for the project scheduling instances in this folder.

## What it does

- Parses the ProGenMax `.SCH` files in `sm_j10` and `sm_j20`
- Handles generalized lag constraints of the form `S_j >= S_i + lag`
- Builds a fast incumbent with a conflict-repair heuristic
- Improves or proves more cases with conflict-set branch-and-bound
- Benchmarks folders of instances from the command line
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

The benchmark command prints aggregate metrics and optionally writes per-instance results to JSON.
