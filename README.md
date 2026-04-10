# RCPSP Solver

This repository contains the CS202 Resource-Constrained Project Scheduling Problem solver and the report-facing rerun harness.

## Executive Summary

The project solves the Resource-Constrained Project Scheduling Problem (RCPSP): each activity has a duration, precedence constraints, and renewable-resource demands, and the goal is to minimize makespan without violating precedence or resource capacity.

The final solver is a hybrid pipeline built from:
- activity-list representation
- Serial Schedule Generation Scheme (SSGS) decoding
- heuristic seeding with priority rules
- genetic search
- forward-backward improvement

The solver is designed as a strong time-budgeted heuristic rather than an exact optimizer. It searches over precedence-feasible activity orders, then uses SSGS to decode each order into a concrete schedule. The final report-facing workflow validates the solver on the local `J10` and `J20` sets and measures the main quantitative results on the PSPLIB `J30`, `J60`, `J90`, and `J120` datasets.

Using the final solver line and a `3s` wall-clock budget, the report states:
- `J30`: `428 / 480` best-known matches, `99.783%` mean quality
- `J60`: `353 / 480` best-known matches, `98.961%` mean quality
- `J90`: `352 / 480` best-known matches, `98.573%` mean quality
- `J120`: `180 / 600` best-known matches, `95.736%` mean quality

The overall pattern is that the solver is very strong on small and medium PSPLIB instances, and degrades gradually as the instances become larger and more constrained.

## Repository Workflow

The repository is organized around the workflow used in [Final_report.md](Final_report.md):
- validation on `J10` and `J20`
- Experiment 1: algorithm component ablation
- Experiment 2: scaling across instance sizes
- Experiment 3: time-budget sensitivity
- Experiment 4: priority-rule comparison

The solver uses:
- activity-list representation
- Serial Schedule Generation Scheme (SSGS) decoding
- heuristic seeding
- genetic search
- forward-backward improvement

It does not include the older tuning-only flows such as restart-threshold refinement, hard-instance quick benches, or development-only benchmark branches.

## Prerequisites

- Python 3
- a C++17 compiler
- PSPLIB datasets already present under `datasets/psplib/`

## Build

On Unix-like environments:

```bash
make
```

On Windows, if `make` is unavailable, compile the solver directly. This static-link form avoids the common MinGW runtime DLL mismatch:

```powershell
g++ -std=c++17 -O2 -march=native -flto -Wall -Wextra -static-libstdc++ -static-libgcc -Isrc -o solver `
  src/main.cpp src/parser.cpp src/ssgs.cpp src/validator.cpp `
  src/priority.cpp src/ga.cpp src/improvement.cpp
```

That produces `solver.exe` on Windows and `solver` on Unix-like systems.

## Main Command

The single entrypoint is:

```bash
python3 scripts/run_report_harness.py --clean
```

Or build and run in one step:

```bash
python3 scripts/run_report_harness.py --build-cmd "make" --clean
```

For Windows PowerShell:

```powershell
python scripts\run_report_harness.py --clean
```

By default the harness runs:
- validation
- Experiment 1
- Experiment 2
- Experiment 3
- Experiment 4

and writes fresh outputs under `report_runs/latest/`.

## Running Specific Stages

```bash
python3 scripts/run_report_harness.py --stage validation
python3 scripts/run_report_harness.py --stage experiment1
python3 scripts/run_report_harness.py --stage experiment2
python3 scripts/run_report_harness.py --stage experiment3
python3 scripts/run_report_harness.py --stage experiment4
```

Multiple stages can be combined:

```bash
python3 scripts/run_report_harness.py --stage validation --stage experiment2 --stage experiment4
```

## Useful Debug Options

```bash
python3 scripts/run_report_harness.py --stage experiment1 --limit 10
python3 scripts/run_report_harness.py --stage experiment2 --match j301
python3 scripts/run_report_harness.py --keep-all-artifacts
python3 scripts/run_report_harness.py --output-root report_runs/debug_small --limit 5
```

## Custom Stage Overrides

The report harness keeps the default report experiments intact, but it now also supports stage-level overrides for dataset subsets, time budgets, and solver configuration.

Available override flags:
- `--validation-datasets`, `--validation-time`, `--validation-mode`
- `--experiment1-datasets`, `--experiment1-configs`, `--experiment1-time`
- `--experiment2-datasets`, `--experiment2-time`, `--experiment2-mode`
- `--experiment3-datasets`, `--experiment3-time-budgets`, `--experiment3-mode`
- `--experiment4-datasets`, `--experiment4-rules`, `--experiment4-time`

Examples:

```bash
python3 scripts/run_report_harness.py --stage experiment2 --experiment2-datasets j60,j90 --experiment2-time 10
python3 scripts/run_report_harness.py --stage experiment3 --experiment3-datasets j60 --experiment3-time-budgets 2,4,8
python3 scripts/run_report_harness.py --stage experiment1 --experiment1-datasets j30 --experiment1-configs baseline,full --experiment1-time 1
python3 scripts/run_report_harness.py --stage experiment4 --experiment4-datasets j30 --experiment4-rules lft,mts --experiment4-time 3
```

PowerShell equivalents:

```powershell
python scripts\run_report_harness.py `
  --stage experiment2 `
  --experiment2-datasets j60,j90 `
  --experiment2-time 10

python scripts\run_report_harness.py `
  --stage experiment3 `
  --experiment3-datasets j60 `
  --experiment3-time-budgets 2,4,8

python scripts\run_report_harness.py `
  --stage experiment1 `
  --experiment1-datasets j30 `
  --experiment1-configs baseline,full `
  --experiment1-time 1

python scripts\run_report_harness.py `
  --stage experiment4 `
  --experiment4-datasets j30 `
  --experiment4-rules lft,mts `
  --experiment4-time 3
```

The stage-level `comparison.md` and `comparison.json` files automatically adapt to the selected subset of runs, so you can use the same harness both for canonical report reruns and smaller exploratory slices.

## Default Stage Definitions

### Validation

- datasets: `J10`, `J20`
- solver config: `--time 3 --mode full`
- per-instance timeout: `5s`

This stage checks parser, decoder, feasibility, and runtime behavior on the provided local `.SCH` sets.

Important note:
- the local `J10` and `J20` sets contain some known infeasible inputs
- the harness records those as `infeasible_input`
- they are reported separately and do not fail the validation stage

### Experiment 1

- datasets: `J30`, `J60`
- configurations:
  - `baseline`: `--time 3 --mode baseline`
  - `priority`: `--time 3 --mode priority`
  - `ga`: `--time 3 --mode ga`
  - `full`: `--time 3 --mode full`
- per-instance timeout: `5s`

### Experiment 2

- datasets: `J30`, `J60`, `J90`, `J120`
- configuration: `--time 3 --mode full`
- per-instance timeout: `5s`

### Experiment 3

- datasets: `J30`, `J60`
- configurations:
  - `1s`: `--time 1 --mode full`, timeout `3s`
  - `3s`: `--time 3 --mode full`, timeout `5s`
  - `10s`: `--time 10 --mode full`, timeout `12s`
  - `28s`: `--time 28 --mode full`, timeout `30s`

### Experiment 4

- datasets: `J30`, `J60`
- configurations:
  - `--time 3 --rule random`
  - `--time 3 --rule lft`
  - `--time 3 --rule mts`
  - `--time 3 --rule grd`
  - `--time 3 --rule spt`
- per-instance timeout: `5s`

Note:
- the harness will pass the configured `--time` value to Experiment 4
- the current solver's standalone `--rule` path is still a single-pass rule decode rather than a time-budgeted search loop

## Outputs

Fresh harness outputs are written to:

```text
report_runs/latest/
```

Each stage gets:
- per-run `results.csv`
- per-run `summary.json`
- stage-level `comparison.json`
- stage-level `comparison.md`

The harness also writes:
- `report_runs/latest/manifest.json`
- `report_runs/latest/manifest.md`

Example layout:

```text
report_runs/latest/
  manifest.json
  manifest.md
  validation/
    comparison.json
    comparison.md
    j10_full/
    j20_full/
  experiment1/
    comparison.json
    comparison.md
    baseline_j30/
    ...
  experiment2/
    comparison.json
    comparison.md
    j30/
    ...
  experiment3/
    comparison.json
    comparison.md
    1s_j30/
    ...
  experiment4/
    comparison.json
    comparison.md
    random_j30/
    ...
```

Each per-run directory contains:
- `results.csv`
- `summary.json`
- `failures/` if any runs failed or if `--keep-all-artifacts` was used

## Interpreting Results

- Validation is mainly about feasibility and runtime behavior on `J10` and `J20`.
- Experiments 1-4 are the canonical report rerun outputs.
- Use the stage-level `comparison.md` files to rebuild the report tables quickly.
- Use `summary.json` if you want the raw aggregate values programmatically.
- When you use override flags, the stage summaries only include the runs you selected.

## Benchmark Driver

The rerun flow is implemented in:
- [scripts/run_report_harness.py](scripts/run_report_harness.py)
- [scripts/benchmark_rcpsp.py](scripts/benchmark_rcpsp.py)

`benchmark_rcpsp.py` is the reusable low-level benchmark runner. `run_report_harness.py` is the report-specific orchestrator that builds the validation and experiment outputs used in the final report.

For PowerShell, prefer the report harness for custom runs because it avoids JSON quoting. Example:

```powershell
python scripts\run_report_harness.py `
  --stage experiment2 `
  --experiment2-datasets j30 `
  --experiment2-time 5
```

If you do use `benchmark_rcpsp.py` directly in PowerShell, wrap `--solver-args-json` in single quotes:

```powershell
python scripts\benchmark_rcpsp.py run `
  --dataset j30 `
  --solver .\solver.exe `
  --solver-args-json '["--time","5","--mode","full"]' `
  --timeout 7 `
  --output-dir benchmark_results\j30_5s_full
```

## Troubleshooting

### `solver not found`

Build the solver first. On Windows, the binary will usually be `solver.exe`.

### `make is not recognized`

Do not rely on `make` on Windows unless it is installed and on the Windows `PATH`. Use the direct `g++` build command instead.

### Windows loader error like `0xC000007B`

Rebuild with:

```powershell
g++ -std=c++17 -O2 -march=native -flto -Wall -Wextra -static-libstdc++ -static-libgcc -Isrc -o solver `
  src/main.cpp src/parser.cpp src/ssgs.cpp src/validator.cpp `
  src/priority.cpp src/ga.cpp src/improvement.cpp
```

### Validation finishes with some infeasible counts

That is expected on the local `J10` and `J20` sets. The harness reports them separately and does not treat them as a validation failure.

## Datasets

| Dataset | Instances | Activities | Format |
|---|---:|---:|---|
| J10 | 270 | 10 | local `.SCH` |
| J20 | 270 | 20 | local `.SCH` |
| J30 | 480 | 30 | PSPLIB `.sm` |
| J60 | 480 | 60 | PSPLIB `.sm` |
| J90 | 480 | 90 | PSPLIB `.sm` |
| J120 | 600 | 120 | PSPLIB `.sm` |

`J10` and `J20` are used only for validation in the report-facing workflow. The main quantitative report results come from `J30`, `J60`, `J90`, and `J120`.
