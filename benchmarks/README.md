# Benchmark Data Layout

Benchmark instances are stored under `benchmarks/data/`.

## Included datasets

- `sm_j10`
- `sm_j20`
- `sm_j30`
- `testset_ubo20`
- `testset_ubo50`
- `testset_ubo100`
- `testset_ubo200`

Each dataset folder contains `.SCH` instances and (when available) `optimum/optimum.csv` reference values.

## Notes

- The CLI accepts both:
  - shorthand dataset names (for example `sm_j10`)
  - explicit paths (for example `benchmarks/data/sm_j10`)
- Keep benchmark files unchanged for fair comparison and reproducibility.
