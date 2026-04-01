#!/bin/bash
# Experiment 1: Algorithm Component Ablation
# Runs 4 solver configurations on J30 and J60, stores results in experiments/results/ablation/

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
RESULTS_DIR="$SCRIPT_DIR/../results"
BENCHMARK="$PROJECT_DIR/scripts/benchmark_rcpsp.py"

cd "$PROJECT_DIR"

# Build solver
make

MODES="baseline priority ga full"
DATASETS="j30 j60"

for mode in $MODES; do
    for dataset in $DATASETS; do
        outdir="$RESULTS_DIR/${mode}_${dataset}"
        echo "========================================"
        echo "Running: mode=$mode dataset=$dataset"
        echo "Output:  $outdir"
        echo "========================================"
        python3 "$BENCHMARK" run \
            --dataset "$dataset" \
            --solver "$SCRIPT_DIR/solver_${mode}.sh" \
            --timeout 5 \
            --output-dir "$outdir"
        echo ""
    done
done

echo "All ablation runs complete. Results in $RESULTS_DIR/"
