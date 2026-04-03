# Experiment 1: Algorithm Component Ablation

## Goal

Quantify the individual contribution of each algorithm component (priority rules, GA, forward-backward improvement) by disabling them one at a time and measuring the impact on solution quality.

## Configurations

| Config | Priority Rules | GA | Forward-Backward | Description |
|--------|:-:|:-:|:-:|---|
| Baseline | No | No | No | Random topological order + SSGS |
| Priority only | Yes | No | No | Best of 4 rules + 20 random, SSGS only |
| GA only | No | Yes | No | Random init population + GA, no improvement |
| Full pipeline | Yes | Yes | Yes | Current solver as-is |

## Datasets

- J30 (480 instances, 30 activities)
- J60 (480 instances, 60 activities)

## Metrics

- **Mean gap to best known (%)** — average percentage above the best known makespan
- **Number of optimal solutions found** — count of instances matching the best known value
- **Mean quality vs best known (%)** — normalised score where 100% = matched reference

## Success Criteria

- All 4 configurations run on J30 and J60 without errors
- Each component shows measurable improvement over the configuration without it
- Results clearly show which component contributes the most to solution quality
- Results tabulated for the report

## How to Run

```bash
# From the project root
make
./experiments/experiment1/scripts/run_ablation.sh
```

`run_ablation.sh` now runs sequentially so the component comparison is measured without concurrent benchmark noise.

Individual modes can also be tested directly:

```bash
./solver <instance_file> --time 3 --mode baseline
./solver <instance_file> --time 3 --mode priority
./solver <instance_file> --time 3 --mode ga
./solver <instance_file> --time 3 --mode full
```

## Results

Stored in `results/` as `<mode>_<dataset>/summary.json` and `results.csv`.
