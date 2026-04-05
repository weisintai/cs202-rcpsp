# Experiment 2: Scaling Across Instance Sizes

## Goal

Demonstrate how solver performance degrades as instance size increases, using the same time budget across all datasets.

## Configurations

- Full pipeline solver (`--mode full`, `--time 3`)
- Run on J30, J60, J90, J120

## Datasets

- J30 (480 instances, 30 activities)
- J60 (480 instances, 60 activities)
- J90 (480 instances, 90 activities)
- J120 (600 instances, 120 activities)

## Metrics

- **Mean gap to best known (%)** — average percentage above the best known makespan
- **Optimal match rate (%)** — percentage of instances matching the best known value
- **Max gap to best known (%)** — worst-case gap across all instances
- **Mean wall time (s)** — average solver runtime per instance

## Success Criteria

- Results available for all 4 datasets
- Clear trend visible: performance degrades with instance size
- Results tabulated and suitable for a line/bar chart in the report

## How to Run

```bash
# From the project root
make
./experiments/experiment2/scripts/run_scaling.sh
```

`run_scaling.sh` now runs datasets sequentially because that is the cleaner default for report-facing wall-clock numbers.

If you want to run the datasets one by one manually, the equivalent commands are:

```bash
python3 scripts/benchmark_rcpsp.py run --dataset j30 --solver ./experiments/experiment2/scripts/solver_full.sh --timeout 5 --output-dir benchmark_results/seq_3s_j30
python3 scripts/benchmark_rcpsp.py run --dataset j60 --solver ./experiments/experiment2/scripts/solver_full.sh --timeout 5 --output-dir benchmark_results/seq_3s_j60
python3 scripts/benchmark_rcpsp.py run --dataset j90 --solver ./experiments/experiment2/scripts/solver_full.sh --timeout 5 --output-dir benchmark_results/seq_3s_j90
python3 scripts/benchmark_rcpsp.py run --dataset j120 --solver ./experiments/experiment2/scripts/solver_full.sh --timeout 5 --output-dir benchmark_results/seq_3s_j120
```

## Results

The current report-facing `3s` wall-clock results are stored in this folder under `results/`.
Older refinement checkpoints remain under `benchmark_results/`.
