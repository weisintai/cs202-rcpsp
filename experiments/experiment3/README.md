# Experiment 3: Time Budget Sensitivity

## Goal

Show the solver's anytime property — solution quality improves with more computation time, and a valid schedule is always available.

## Configurations

- Full pipeline solver (`--mode full`)
- GA time budgets: 1s, 3s, 10s, 28s
- Benchmark timeout set to GA time + 2s to allow for parsing/output overhead

## Datasets

- J30 (480 instances, 30 activities)
- J60 (480 instances, 60 activities)

## Metrics

- **Mean gap to best known (%)** — average percentage above the best known makespan at each time budget
- **Optimal match rate (%)** — percentage of instances matching the best known value at each time budget
- **Mean quality vs best known (%)** — normalised score at each time budget

## Success Criteria

- All 4 time budgets complete without errors on both datasets
- Monotonic improvement: longer time budget never produces worse mean results
- Diminishing returns visible (large improvement from 1s to 3s, smaller from 10s to 28s)
- Results tabulated for a quality-vs-time chart

## How to Run

```bash
# From the project root
make
./experiments/experiment3/scripts/run_time_sensitivity.sh
```

`run_time_sensitivity.sh` now runs sequentially so the time-quality comparison is measured without concurrent benchmark noise.

## Results

Stored in `results/` as `<time>s_<dataset>/summary.json` and `results.csv`.

This experiment is currently **frozen on the solver line immediately before the latest GA upgrade**. Its role in the report is to demonstrate anytime behaviour: giving the solver more time improves average results, with diminishing returns. It should not be treated as the latest absolute-quality benchmark for the current final solver line unless it is rerun.
