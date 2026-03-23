# RCPSP/max Solver

In-repo RCPSP/max solver and experiment harness for the course project. The current submission-oriented workflow targets the custom `cp` backend; `hybrid` remains a comparison baseline and `sgs` remains a secondary backend track.

Raw benchmark datasets now live under `benchmarks/data/` to keep the project root cleaner. The CLI still accepts the old shorthand dataset names such as `sm_j10` and `testset_ubo50`.

## Project layout

- [rcpsp/README.md](rcpsp/README.md)
  - package index and shared module layout
- [rcpsp/heuristic/README.md](rcpsp/heuristic/README.md)
  - legacy heuristic baseline
- [rcpsp/cp/README.md](rcpsp/cp/README.md)
  - current submission-candidate backend
- [CP_ROADMAP.md](CP_ROADMAP.md)
  - phased implementation plan for the CP backend
- [rcpsp/sgs/README.md](rcpsp/sgs/README.md)
  - clean SGS-first backend
- [SGS_ROADMAP.md](SGS_ROADMAP.md)
  - phased implementation plan for the SGS backend
- [references/README.md](references/README.md)
  - external reference repos cloned for study

## What it does

- Parses ProGenMax `.SCH` files across the benchmark folders in this repo, including `sm_j10`, `sm_j20`, `sm_j30`, `testset_ubo20`, and `testset_ubo50`
- Handles generalized lag constraints of the form `S_j >= S_i + lag`
- Exposes three in-repo backends: `cp`, `hybrid`, and `sgs`
- Uses the `cp` backend as the current submission-candidate path for branch-and-propagate search under the assignment constraints
- Keeps `hybrid` available as a practical baseline for comparison runs
- Benchmarks folders of instances from the command line
- Compares benchmark outputs against published reference values for `sm_j10`, `sm_j20`, `sm_j30`, `testset_ubo20`, and `testset_ubo50`
- Reports `feasible`, `infeasible`, or `unknown` per instance
- Records assignment-faithful wall-clock runtime per instance and also keeps backend-only runtime for diagnosis

## Usage

Unless you are explicitly comparing backends, assume `cp` is the backend to run for iteration and for final submission checks.

Solve one instance:

```bash
uv run main.py solve sm_j10/PSP1.SCH --time-limit 1.0 --backend cp
uv run main.py solve benchmarks/data/sm_j10/PSP1.SCH --time-limit 1.0 --backend cp
```

You can switch solver backends explicitly:

```bash
uv run main.py solve sm_j10/PSP1.SCH --time-limit 1.0 --backend hybrid
uv run main.py solve sm_j10/PSP1.SCH --time-limit 1.0 --backend cp
uv run main.py solve sm_j10/PSP1.SCH --time-limit 1.0 --backend sgs
```

Benchmark a full folder:

```bash
uv run main.py benchmark sm_j10 --time-limit 0.1 --backend cp --output sm_j10_results.json --no-progress
uv run main.py benchmark benchmarks/data/sm_j10 --time-limit 0.1 --backend cp --output sm_j10_results.json --no-progress
```

Run the default CP iteration suite in one command:

```bash
uv run python scripts/run_guardrails.py
uv run python scripts/run_guardrails.py --preset submission_quick
```

The default command above currently means `--backend cp --preset submission_quick`.

Run the CP-focused autoresearch evaluation loop:

```bash
uv run python scripts/run_autoresearch_eval.py
uv run python scripts/run_autoresearch_eval.py --backend cp --preset submission_quick
```

Run an auxiliary anti-overfitting sweep on broader public RCPSP/max sets from the Kobe corpus:

```bash
uv run python scripts/run_guardrails.py --backend cp --preset broad_generalization
```

Run the dedicated 30-second CP acceptance matrix:

```bash
uv run python scripts/run_guardrails.py --backend cp --preset cp_acceptance
uv run python scripts/run_guardrails.py --backend cp --preset submission
```

`cp_acceptance` is the public 30-second matrix. `submission` extends that run with held-out `ubo10/100/200 @ 0.1s` anti-overfitting checks.

If `sm_j10` and `sm_j20` reference CSVs are missing locally, cache them first:

```bash
uv run python scripts/fetch_reference_csvs.py --datasets sm_j10 sm_j20
```

The root [program.md](program.md) is an RCPSP-specific adaptation of the `karpathy/autoresearch` workflow for this repo.

`benchmark` now prints live progress to `stderr` by default. The automated harness disables progress to reduce timing noise. Use `--no-progress` for manual runs when you want only the final summary:

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
- `testset_ubo10`
- `testset_ubo20`
- `testset_ubo50`
- `testset_ubo100`
- `testset_ubo200`
- `testset_ubo500`
- `testset_ubo1000`

`compare` now prefers a local `benchmarks/data/<dataset>/optimum/optimum.csv` when present and falls back to the public URL otherwise.

The benchmark command prints aggregate metrics and optionally writes per-instance results to JSON.

## Benchmark Guardrails

Do not evaluate solver changes on `sm_j10` and `sm_j20` alone.

Every solver change should be screened on:

- `sm_j10`
  - easy-set correctness and regression check
- `sm_j20`
  - main public quality target
- `sm_j30`
  - broader family guardrail
- `testset_ubo50`
  - hardest public stress test currently in the repo

Recommended validation loop:

1. fast CP screen aligned with the submission backend
   - `uv run python scripts/run_guardrails.py --preset submission_quick`
2. if the change survives, run the held-out anti-overfitting suite
   - `uv run python scripts/run_guardrails.py --preset broad_generalization`
3. before calling a change submission-ready, run the 30-second matrix
   - `uv run python scripts/run_guardrails.py --preset cp_acceptance`
4. only keep changes that improve the target set without clearly damaging the broader guardrails

This is the minimum anti-overfitting policy for the repo. A change that helps only `j10/j20` but hurts `sm_j30` or `ubo50` should be treated as suspect.

For the final submission backend, use `cp` and the stricter roadmap matrix in [CP_ROADMAP.md](CP_ROADMAP.md).

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
  - results that exceed the time limit by more than a small tolerance are coerced to `unknown`
- `solver_runtime_seconds`
  - backend-only runtime excluding CLI parse and wrapper overhead
  - useful for diagnosing solver changes without losing the assignment-faithful wall-clock metric
- `over_budget`
  - `1` if the recorded wall-clock runtime exceeded the allowed budget plus tolerance, else `0`

For whole-benchmark comparisons, the most useful summary fields are:

1. `feasible`
2. `unknown`
3. `over_budget`
4. `avg_ratio`
5. `avg_runtime_seconds`

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
