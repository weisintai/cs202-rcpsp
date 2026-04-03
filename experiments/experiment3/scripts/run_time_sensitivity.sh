#!/bin/bash
# Experiment 3: Time Budget Sensitivity
# Runs full pipeline at 1s, 3s, 10s, 28s GA budgets on J30 and J60
# Runs sequentially to keep wall-clock comparisons clean

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
RESULTS_DIR="$SCRIPT_DIR/../results"
BENCHMARK="$PROJECT_DIR/scripts/benchmark_rcpsp.py"

cd "$PROJECT_DIR"

make

for ga_time in 1 3 10 28; do
    timeout=$((ga_time + 2))
    for dataset in j30 j60; do
        outdir="$RESULTS_DIR/${ga_time}s_${dataset}"
        echo "Running sequential benchmark: ga_time=${ga_time}s dataset=$dataset timeout=${timeout}s"
        python3 "$BENCHMARK" run \
            --dataset "$dataset" \
            --solver "$SCRIPT_DIR/solver_${ga_time}s.sh" \
            --timeout "$timeout" \
            --output-dir "$outdir"
    done
done

python3 "$SCRIPT_DIR/summarise_time_sensitivity.py" "$RESULTS_DIR"

echo "All sequential time sensitivity runs complete. Results in $RESULTS_DIR/"
