# Scripts Guide

This folder contains helper scripts for running benchmark screens, residue analysis, and reference-data setup.

## Core scripts

- `run_guardrails.py`
  - main driver for preset benchmark suites via `guardrails_lib.py`
- `run_cp_residue.py`
  - fast loop on hard public CP residue instances
- `guardrails_lib.py`
  - preset definitions and execution/reporting utilities used by guardrail runs

## Analysis and utility scripts

- `analyze_cp_residue.py`
  - reruns misses from a benchmark JSON and summarizes likely miss reasons
- `sweep_time_budget.py`
  - runs one backend across multiple time budgets and writes aggregate sweep output
- `fetch_reference_csvs.py`
  - caches public reference `optimum.csv` files under `benchmarks/data`

## Common usage

Run the submission quick screen:

```bash
python3 scripts/run_guardrails.py --backend cp --preset submission_quick
```

Run the 30-second acceptance screen:

```bash
python3 scripts/run_guardrails.py --backend cp --preset cp_acceptance
```

Run the CP residue set:

```bash
python3 scripts/run_cp_residue.py --time-limit 30.0
```
