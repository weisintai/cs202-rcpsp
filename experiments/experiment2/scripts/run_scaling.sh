#!/bin/bash
# Experiment 2: Scaling Across Instance Sizes
# Runs full pipeline on J30, J60, J90, J120 with the same time budget
# Runs sequentially to avoid cross-dataset CPU contention in wall-clock results

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
RESULTS_DIR="$SCRIPT_DIR/../results"
BENCHMARK="$PROJECT_DIR/scripts/benchmark_rcpsp.py"

cd "$PROJECT_DIR"

make
DATASETS="${DATASETS:-j30 j60 j90 j120}"

for dataset in $DATASETS; do
    outdir="$RESULTS_DIR/${dataset}"
    echo "Running sequential benchmark: dataset=$dataset"
    python3 "$BENCHMARK" run \
        --dataset "$dataset" \
        --solver "$SCRIPT_DIR/solver_full.sh" \
        --timeout 5 \
        --output-dir "$outdir"
done

python3 "$SCRIPT_DIR/summarise_scaling.py" "$RESULTS_DIR"

echo "All sequential scaling runs complete. Results in $RESULTS_DIR/"
