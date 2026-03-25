# RCPSP/max Solver

In-repo RCPSP/max solver and experiment harness for the course project. The active submission-oriented workflow now targets the custom `cp` backend. `cp_full` is the experimental fuller-CP track for architectural work. `hybrid` and `sgs` are kept in the repo as historical comparison baselines and idea sources, not as the main iteration path.

Raw benchmark datasets now live under `benchmarks/data/` to keep the project root cleaner. The CLI still accepts the old shorthand dataset names such as `sm_j10` and `testset_ubo50`.

## Project layout

- [rcpsp/README.md](rcpsp/README.md)
  - package index and shared module layout
- [rcpsp/cp/README.md](rcpsp/cp/README.md)
  - current submission-candidate backend
- [rcpsp/cp_full/README.md](rcpsp/cp_full/README.md)
  - experimental fuller-CP backend
- [CP_ROADMAP.md](CP_ROADMAP.md)
  - phased implementation plan for the CP backend
- [CP_FULL_ROADMAP.md](CP_FULL_ROADMAP.md)
  - architectural charter for the fuller-CP track
- [report.md](report.md)
  - project report notes and submission positioning
- [rcpsp/heuristic/README.md](rcpsp/heuristic/README.md)
  - archived heuristic baseline
- [rcpsp/sgs/README.md](rcpsp/sgs/README.md)
  - archived SGS-style comparison backend
- [SGS_ROADMAP.md](SGS_ROADMAP.md)
  - historical SGS roadmap
- [references/README.md](references/README.md)
  - external reference repos cloned for study

## What it does

- Parses ProGenMax `.SCH` files across the benchmark folders in this repo, including `sm_j10`, `sm_j20`, `sm_j30`, `testset_ubo20`, and `testset_ubo50`
- Handles generalized lag constraints of the form `S_j >= S_i + lag`
- Uses the `cp` backend as the active submission-candidate path for branch-and-propagate search under the assignment constraints
- Keeps `cp_full` as the experimental branch for larger architectural CP changes
- Implements the current `cp` backend around lag-closure propagation, compulsory-part / timetable pruning, pair-order branching, and a local guided-seed warm start
- Keeps `hybrid` and `sgs` only as comparison baselines for side-by-side checks
- Benchmarks folders of instances from the command line
- Compares benchmark outputs against published reference values for `sm_j10`, `sm_j20`, `sm_j30`, `testset_ubo20`, and `testset_ubo50`
- Reports `feasible`, `infeasible`, or `unknown` per instance
- Records assignment-faithful wall-clock runtime per instance and also keeps backend-only runtime for diagnosis

## Usage

Unless you are explicitly comparing backends, assume `cp` is the backend to run for iteration and for final submission checks. Use `cp_full` only when you are deliberately testing architectural changes.

Solve one instance:

```bash
uv run main.py solve sm_j10/PSP1.SCH --time-limit 1.0 --backend cp
uv run main.py solve benchmarks/data/sm_j10/PSP1.SCH --time-limit 1.0 --backend cp
```

For a teammate handoff on how the active solver works, start with [rcpsp/cp/README.md](rcpsp/cp/README.md). It gives the CP mental model, solve flow, key files, and the recommended iteration loop.

For the experimental fuller-CP track, start with [rcpsp/cp_full/README.md](rcpsp/cp_full/README.md) and [CP_FULL_ROADMAP.md](CP_FULL_ROADMAP.md).

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

Run the small CP residue set when you want a fast signal on the hard public `30s` misses:

```bash
uv run python scripts/run_cp_residue.py
```

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

For the final submission backend, use `cp` and the stricter roadmap matrix in [CP_ROADMAP.md](CP_ROADMAP.md). Treat `cp_full` as experimental until it beats `cp` on the same screens and remains stable. Treat `hybrid` and `sgs` as archived comparison paths unless a change specifically needs a baseline comparison.

## Current Backend Snapshot

Fresh reruns on the current checkout still support the repo split between `hybrid` and `cp`, but the numbers are not the older ones in `ITERATION_NOTES.md`.

- `sm_j30 @ 0.1s`
  - `hybrid`: `172 feasible / 85 infeasible / 13 unknown`
  - `hybrid` compare: `83/120` exact, exact-match rate `69.2%`, avg exact ratio `1.0207`
  - `cp`: `165 feasible / 85 infeasible / 20 unknown`
  - `cp` compare: `75/120` exact, exact-match rate `62.5%`, avg exact ratio `1.0406`
- `sm_j20 @ 1.0s`
  - `hybrid`: `184 feasible / 86 infeasible / 0 unknown`
  - `hybrid` compare: `125/158` exact, exact-match rate `79.1%`, avg exact ratio `1.0167`
  - `cp`: `184 feasible / 86 infeasible / 0 unknown`
  - `cp` compare: `155/158` exact, exact-match rate `98.1%`, avg exact ratio `1.0009`
- `sm_j30 @ 30.0s`
  - `cp`: `184 feasible / 85 infeasible / 1 unknown`
  - `cp` compare: `117/120` exact, exact-match rate `97.5%`

Practical read:

- `hybrid` is still the stronger short-budget comparison baseline on `sm_j30 @ 0.1s`
- `cp` is the clearly stronger medium-budget submission backend on `sm_j20 @ 1.0s`
- `cp` now also looks healthy on the public `sm_j30 @ 30.0s` acceptance row after fixing the long-budget overrun path
- both statements are based on the fresh reruns above, after hardening the `hybrid` repair path against infeasible local repair projections

## CP Backend Read

The current `cp` solver is following a standard `RCPSP/max` CP shape:

- temporal closure over generalized precedence / lag constraints
- cumulative-capacity reasoning through compulsory-part / timetable propagation
- search over additional pair-order resource decisions
- branch-and-bound with an incumbent makespan
- a local `guided_seed` phase to try to find an early incumbent before DFS

That is the right model family for `RCPSP/max`. What it is not yet is a full-strength scheduling CP engine.

Missing pieces compared with stronger scheduling CP solvers:

- timetable-edge-finding or similarly strong cumulative propagation
- richer `not-first / not-last` inference
- smaller reusable overload explanations / failure cores
- more incremental propagation scheduling instead of mostly recompute-to-fixpoint
- stronger incumbent generation on hard feasible large instances

This is why the current CP iteration policy treats `0.1s` and `30s` as different operating regimes. Some deeper reasoning is promising, but it must stay gated so the short-budget acceptance path stays stable.

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

These are the stronger-CP ideas that still fit the current project scope and codebase:

- stronger cumulative propagation such as `TTEF-lite`, energetic-window checks, and better overload-core shrinking
- richer `not-first / not-last` and conflict-derived pair forcing
- better exact-search branching using explanation tightness, conflict history, or activity failure counts
- stronger incumbent generation and repair on hard feasible cases before DFS burns the full budget
- more explicit separation between cheap always-on propagation and deeper-budget propagation

What we are deliberately not trying to build from scratch right now:

- a full `lazy clause generation` engine
- a full external-solver-grade cumulative propagator stack
- a full external-solver-grade CP / MIP engine

Those are valid research directions, but they are much larger engineering projects than this assignment needs.

## References

Public solver and model references cloned for local study live in [references/README.md](references/README.md).
