# RCPSP Solver

A solver for the Resource Constrained Project Scheduling Problem (RCPSP) built for CS202. Given a set of activities with durations, resource demands, and precedence constraints, the solver minimises the project makespan while ensuring resource capacity is never exceeded at any timestep.

## Algorithm

The solver uses a Genetic Algorithm with a Serial Schedule Generation Scheme (SSGS) decoder. The pipeline:

1. **Parse** input file (`.sm` or `.SCH` format)
2. **Generate initial solutions** using priority rules (LFT, MTS, GRD, SPT) and biased randomized permutations (LFT/MTS-weighted seeding)
3. **Decode** each activity order with SSGS to obtain a feasible schedule
4. **Evolve** the population using tournament selection, hybrid crossover, adaptive mutation, and a richer activity-list mutation neighborhood
5. **Diversify** with restart-on-stagnation and duplicate-aware population control when the GA plateaus
6. **Improve** strong candidates with forward-backward double justification
7. **Validate and output** start times for each activity

## Build

Requires a C++17 compiler (g++ or clang++).

```bash
make              # optimised build
make debug        # debug build with AddressSanitizer
make clean        # remove binaries
```

## Usage

```bash
./solver <instance_file> [options]
```

### Options

| Flag | Description | Default |
|------|-------------|---------|
| `--time <seconds>` | GA time budget in seconds | `28` |
| `--schedules <count>` | Optional GA schedule-generation budget for internal A/B tests | disabled |
| `--mode <mode>` | Algorithm mode (see below) | `full` |
| `--rule <rule>` | Run a single priority rule + SSGS (see below) | not set |

### Modes

| Mode | Description |
|------|-------------|
| `full` | Full pipeline: guided seeds + GA + restart-on-stagnation + duplicate-aware diversity control + forward-backward improvement |
| `baseline` | Random topological order + SSGS only |
| `priority` | Best of priority rules + random permutations, no GA |
| `ga` | Random initial population + GA, no forward-backward improvement |

### Rules

When `--rule` is set, the solver ignores `--mode` and `--time`, and produces a single solution using the specified priority rule + SSGS.

| Rule | Priority value |
|------|---------------|
| `lft` | Latest Finish Time (CPM backward pass) |
| `mts` | Most Total Successors (transitive count) |
| `grd` | Greatest Resource Demand (sum across all types) |
| `spt` | Shortest Processing Time (duration) |
| `random` | Random tie-breaking |

### Examples

```bash
# Run with default settings (full pipeline, 28s GA budget)
./solver datasets/psplib/j30/instances/j301_1.sm

# Run with a 5-second GA budget
./solver datasets/psplib/j30/instances/j301_1.sm --time 5

# Run with a schedule-generation budget instead of relying on wall-clock only
./solver datasets/psplib/j30/instances/j301_1.sm --time 999 --schedules 5000

# Run in priority-only mode (no GA)
./solver datasets/psplib/j30/instances/j301_1.sm --mode priority

# Run a single priority rule (LFT)
./solver datasets/psplib/j30/instances/j301_1.sm --rule lft
```

### Output

- **stdout:** Start times for activities 1 through n, one integer per line
- **stderr:** Feasibility check result and makespan

The reported makespan is the true project finish time, i.e. the maximum finish time over all activities. On well-formed PSPLIB instances this is the same as the dummy-sink start time, but the true finish-time definition is more robust for local `.SCH` files where some terminal jobs may not be connected to the sink.

## Benchmarking

Benchmark against PSPLIB instances with known optimal/best-known values:

```bash
make bench-j30     # benchmark all J30 instances (480 files, 30 activities)
make bench-j60     # benchmark all J60 instances (480 files, 60 activities)
make bench-j90     # benchmark all J90 instances (480 files, 90 activities)
make bench-j120    # benchmark all J120 instances (600 files, 120 activities)
```

The benchmark script supports additional options when called directly:

```bash
python3 scripts/benchmark_rcpsp.py run \
    --dataset j30 \
    --solver ./solver \
    --timeout 5 \
    --limit 10 \
    --output-dir results/
```

| Flag | Description |
|------|-------------|
| `--dataset` | Dataset to benchmark: `j10`, `j20`, `j30`, `j60`, `j90`, `j120` |
| `--solver` | Path to solver executable or wrapper script |
| `--timeout` | Per-instance wall-clock timeout in seconds |
| `--limit` | Only run the first N instances |
| `--match` | Only run instances whose filename contains this substring |
| `--instance-list` | Only run exact instance basenames listed in a text file |
| `--output-dir` | Directory for results (CSV + JSON summary) |
| `--build-cmd` | Shell command to build the solver before benchmarking |

Results are written to the output directory as `results.csv` (per-instance) and `summary.json` (aggregate). Key metrics in the summary:

- `gap_to_best_known_pct` — how far the makespan is above the best known value
- `quality_vs_best_known_pct` — normalised score where 100% means matching the reference exactly

For the local `j10` and `j20` datasets, the benchmark harness does not currently include best-known reference tables, so those runs are mainly used for feasibility, runtime, and raw makespan checking.

For internal solver development, the binary also supports `--schedules <count>` as an alternative stopping rule. This counts `SSGS` schedule generations inside the GA and is useful for algorithm-to-algorithm comparison because it is less sensitive to machine speed than wall-clock time. The final project report should still use wall-clock budgets because the assignment itself has a time requirement.

The convenience scripts under `experiments/` often launch multiple benchmark jobs in parallel. That is useful for throughput, but it adds noise to wall-clock-limited runs because datasets compete for CPU time. For report-quality reruns, prefer calling `scripts/benchmark_rcpsp.py run` directly and run datasets sequentially.

Current report-facing `3s` wall-clock results live under `experiments/experiment2/results/`. Curated hard-instance subsets and quick development reruns live under `benchmark_results/hard_instances/` and `benchmark_results/quick_hard_*`.

### Recommended workflow after solver changes

Use this order when testing a new solver idea:

1. **Smoke test locally**
   - run one or two instances directly to check correctness and logging
2. **Internal A/B test with schedule budget**
   - use `--schedules <count>` to compare search quality without mixing in machine-speed effects
   - start with targeted subsets such as known regressions before running large sweeps
3. **Targeted subset benchmark**
   - prefer regression subsets or curated hard-instance lists before running large sweeps
4. **Full `3s` wall-clock sweep**
   - only if the targeted/internal result looks promising
5. **Longer wall-clock confirmation**
   - run `10s` or `28s` only for changes that survive the `3s` comparison

Rule of thumb:
- use **schedule budget** to compare algorithm ideas
- use **wall-clock** to report assignment-facing results

Useful helpers:

```bash
# Regenerate hard-instance subsets from historical runs
python3 scripts/derive_hard_instances.py --top-k 20

# Run curated hard subsets for j30/j60/j90/j120
./scripts/quick_hard_bench.sh 20
```

## Datasets

| Dataset | Instances | Activities | Format |
|---------|-----------|------------|--------|
| J10 | 270 | 10 | `.SCH` (local compact RCPSP-style format) |
| J20 | 270 | 20 | `.SCH` (local compact RCPSP-style format) |
| J30 | 480 | 30 | `.sm` (PSPLIB) |
| J60 | 480 | 60 | `.sm` (PSPLIB) |
| J90 | 480 | 90 | `.sm` (PSPLIB) |
| J120 | 600 | 120 | `.sm` (PSPLIB) |

Datasets live under `datasets/psplib/` (`.sm` format) and `sm_j10/`, `sm_j20/` (`.SCH` format).

Notes on the updated local `j10`/`j20` sets:
- the checked-in local `j10`/`j20` files use a compact `.SCH` layout and are already acyclic, so the solver does not perform any extra precedence-graph repair
- some updated local `.SCH` instances are infeasible as provided because an activity demand exceeds the declared capacity; the benchmark harness records these as `infeasible_input`
- current `3s` full-pipeline benchmark status on the updated sets:
  - J10: `253/270` feasible runs, `17` infeasible input files
  - J20: `266/270` feasible runs, `4` infeasible input files

## Team

- [Member names and student IDs to be added]
