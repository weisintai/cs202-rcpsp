#!/bin/bash
# Experiment 4: Priority Rule Comparison
# Runs 5 configurations (random, lft, mts, grd, spt) on J30 and J60
# Runs sequentially to keep wall-clock comparisons clean

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
RESULTS_DIR="$SCRIPT_DIR/../results"
BENCHMARK="$PROJECT_DIR/scripts/benchmark_rcpsp.py"

cd "$PROJECT_DIR"

make

RULES="random lft mts grd spt"
DATASETS="j30 j60"

for rule in $RULES; do
    for dataset in $DATASETS; do
        outdir="$RESULTS_DIR/${rule}_${dataset}"
        echo "Running sequential benchmark: rule=$rule dataset=$dataset"
        python3 "$BENCHMARK" run \
            --dataset "$dataset" \
            --solver "$SCRIPT_DIR/solver_${rule}.sh" \
            --timeout 5 \
            --output-dir "$outdir"
    done
done

python3 "$SCRIPT_DIR/summarise_priority_comparison.py" "$RESULTS_DIR"

echo "All sequential priority comparison runs complete. Results in $RESULTS_DIR/"
