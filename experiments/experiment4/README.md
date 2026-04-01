# Experiment 4: Priority Rule Comparison

## Goal

Compare the effectiveness of each individual priority rule (LFT, MTS, GRD, SPT) as standalone heuristics, to understand which scheduling intuitions work best for RCPSP.

## Configurations

- Each of the 4 priority rules used alone (single biased topological sort + SSGS)
- Random topological order + SSGS as a control
- Total: 5 configurations

## Datasets

- J30 (480 instances, 30 activities)
- J60 (480 instances, 60 activities)

## Metrics

- **Mean gap to best known (%)** — average percentage above the best known makespan per rule
- **Optimal match rate (%)** — percentage of instances matching the best known value per rule
- **Number of times each rule produces the best result** — count of instances where a given rule beats all others

## Success Criteria

- All 5 configurations run on J30 and J60 without errors
- Clear ranking emerges among the priority rules
- Results tabulated for comparison in the report

## How to Run

```bash
# From the project root
make
./experiments/experiment4/scripts/run_priority_comparison.sh
```

## Results

Stored in `results/` as `<rule>_<dataset>/summary.json` and `results.csv`.
