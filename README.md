# RCPSP Solver

This repository contains a C++ solver for the resource-constrained project scheduling problem (RCPSP).

## Build

```bash
make clean
make
```

## Run One Instance

```bash
./solver datasets/psplib/j30/instances/j3010_1.sm
```

The solver prints one start time per real activity to `stdout`. It prints validation details and the makespan to `stderr`.

## Included PSPLIB Datasets

The repo now includes the official standard single-mode RCPSP datasets and reference files for:

- `j30`
- `j60`
- `j90`
- `j120`

These live under `datasets/psplib/`.

The repo also includes the assignment-provided local benchmark folders:

- `j10` from `sm_j10/`
- `j20` from `sm_j20/`

## Benchmark Your Solver

Run the full `j30` benchmark:

```bash
make bench-j10
make bench-j20
make bench-j30
```

Run the larger official datasets:

```bash
make bench-j60
make bench-j90
make bench-j120
```

The harness writes dataset-specific outputs under `benchmark_results/<dataset>/`:

- per-instance results to `results.csv`
- aggregate summary to `summary.json`
- failure artifacts to `failures/`

The summary includes two comparison styles against PSPLIB references:

- `gap_to_best_known_pct`: how far your makespan is above the best known value
- `quality_vs_best_known_pct`: a normalized score where `100%` means you matched the reference exactly

For `j10` and `j20`, the harness still validates runtime and feasibility, but it does not report reference-gap metrics because those local `.SCH` sets do not currently have a comparable standard RCPSP reference table in this repo.

You can also call the harness directly:

```bash
python3 scripts/benchmark_rcpsp.py run --dataset j10 --solver ./solver --build-cmd make
python3 scripts/benchmark_rcpsp.py run --dataset j20 --solver ./solver --build-cmd make
python3 scripts/benchmark_rcpsp.py run --dataset j30 --solver ./solver --build-cmd make
python3 scripts/benchmark_rcpsp.py run --dataset j60 --solver ./solver --build-cmd make
```
