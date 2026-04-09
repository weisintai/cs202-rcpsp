# Report Rerun Guide

This guide documents the cleaned-up, report-facing experiment harness for the RCPSP solver.

It covers exactly the workflow described in `Final_report.md`:
1. validation on the local `J10` and `J20` sets
2. Experiment 1: algorithm component ablation
3. Experiment 2: scaling across instance sizes
4. Experiment 3: time-budget sensitivity
5. Experiment 4: priority-rule comparison

It does not include the older tuning-only flows such as restart-threshold refinement, hard-instance quick benches, or development-only benchmark branches.

## Prerequisites

- Python 3
- A C++17 compiler
- PSPLIB datasets already present in `datasets/psplib/`

## Build

### Unix-like shells

```bash
make
```

### Windows PowerShell

If `make` is unavailable, compile the solver directly:

```powershell
g++ -std=c++17 -O2 -march=native -flto -Wall -Wextra -static-libstdc++ -static-libgcc -Isrc -o solver `
  src/main.cpp src/parser.cpp src/ssgs.cpp src/validator.cpp `
  src/priority.cpp src/ga.cpp src/improvement.cpp
```

This static-link form is recommended on Windows because it avoids the common MinGW `libstdc++-6.dll` loader mismatch.

## Main Command

From the repository root:

### Unix-like shells

```bash
python3 scripts/run_report_harness.py --clean
```

Or build and run in one step:

```bash
python3 scripts/run_report_harness.py --build-cmd "make" --clean
```

### Windows PowerShell

```powershell
python scripts\run_report_harness.py --clean
```

By default this runs:
- validation
- Experiment 1
- Experiment 2
- Experiment 3
- Experiment 4

and writes fresh outputs to:

```text
report_runs/latest/
```

## Running Only Specific Stages

### Validation only

```bash
python3 scripts/run_report_harness.py --stage validation
```

### Experiment 1 only

```bash
python3 scripts/run_report_harness.py --stage experiment1
```

### Experiment 2 only

```bash
python3 scripts/run_report_harness.py --stage experiment2
```

### Experiment 3 only

```bash
python3 scripts/run_report_harness.py --stage experiment3
```

### Experiment 4 only

```bash
python3 scripts/run_report_harness.py --stage experiment4
```

Multiple stages can be combined:

```bash
python3 scripts/run_report_harness.py --stage validation --stage experiment2 --stage experiment4
```

## Useful Debug Options

Run only the first few instances per benchmark:

```bash
python3 scripts/run_report_harness.py --stage experiment1 --limit 10
```

Restrict to filenames containing a substring:

```bash
python3 scripts/run_report_harness.py --stage experiment2 --match j301
```

Keep stdout/stderr artifacts for every instance:

```bash
python3 scripts/run_report_harness.py --keep-all-artifacts
```

Choose a different output folder:

```bash
python3 scripts/run_report_harness.py --output-root report_runs/debug_small --limit 5
```

## What Each Stage Runs

### Validation

- dataset: `J10`, `J20`
- solver config: `--time 3 --mode full`
- per-instance timeout: `5s`

This stage checks parser/decoder/runtime behavior on the provided local `.SCH` sets.

Important note:
- the local `J10` and `J20` sets contain some known infeasible inputs
- the harness counts those as `infeasible_input`
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
  - `--rule random`
  - `--rule lft`
  - `--rule mts`
  - `--rule grd`
  - `--rule spt`
- per-instance timeout: `5s`

## Output Layout

Example structure:

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

Each stage-level directory contains:
- `comparison.json`
- `comparison.md`

## Interpreting Results

- Validation is mainly about feasibility and runtime behavior on `J10` and `J20`.
- Experiments 1-4 are the canonical report rerun outputs.
- Use the stage-level `comparison.md` files to rebuild the report tables quickly.
- Use `summary.json` if you want the raw aggregate values programmatically.

## Benchmark Driver

The report harness is implemented in:

- `scripts/run_report_harness.py`
- `scripts/benchmark_rcpsp.py`

`benchmark_rcpsp.py` now accepts direct solver arguments, so the harness no longer needs shell-specific wrapper scripts just to pass `--mode`, `--time`, or `--rule`.

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

That is expected on the local `J10` and `J20` sets. The harness reports them separately and does not treat them as a failure of the validation stage.
