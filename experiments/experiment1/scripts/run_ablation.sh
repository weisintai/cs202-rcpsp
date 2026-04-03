#!/bin/bash
# Experiment 1: Algorithm Component Ablation
# Runs 4 solver configurations on J30 and J60
# Runs sequentially to keep wall-clock comparisons clean

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
RESULTS_DIR="$SCRIPT_DIR/../results"
BENCHMARK="$PROJECT_DIR/scripts/benchmark_rcpsp.py"

cd "$PROJECT_DIR"

make

MODES="baseline priority ga full"
DATASETS="j30 j60"

for mode in $MODES; do
    for dataset in $DATASETS; do
        outdir="$RESULTS_DIR/${mode}_${dataset}"
        echo "Running sequential benchmark: mode=$mode dataset=$dataset"
        python3 "$BENCHMARK" run \
            --dataset "$dataset" \
            --solver "$SCRIPT_DIR/solver_${mode}.sh" \
            --timeout 5 \
            --output-dir "$outdir"
    done
done

python3 "$SCRIPT_DIR/summarise_ablation.py" "$RESULTS_DIR"

echo "All sequential ablation runs complete. Results in $RESULTS_DIR/"
