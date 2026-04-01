#!/bin/bash
# Experiment 4: Priority Rule Comparison
# Runs 5 configurations (random, lft, mts, grd, spt) on J30 and J60
# All 10 runs launch in parallel

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
RESULTS_DIR="$SCRIPT_DIR/../results"
BENCHMARK="$PROJECT_DIR/scripts/benchmark_rcpsp.py"

cd "$PROJECT_DIR"

# Build solver
make

# Launch all 10 runs in parallel
pids=()

RULES="random lft mts grd spt"
DATASETS="j30 j60"

for rule in $RULES; do
    for dataset in $DATASETS; do
        outdir="$RESULTS_DIR/${rule}_${dataset}"
        echo "Launching: rule=$rule dataset=$dataset"
        python3 "$BENCHMARK" run \
            --dataset "$dataset" \
            --solver "$SCRIPT_DIR/solver_${rule}.sh" \
            --timeout 5 \
            --output-dir "$outdir" &
        pids+=($!)
    done
done

echo ""
echo "Waiting for ${#pids[@]} parallel runs to complete..."

# Wait for all and track failures
failed=0
for pid in "${pids[@]}"; do
    if ! wait "$pid"; then
        failed=$((failed + 1))
    fi
done

if [ "$failed" -gt 0 ]; then
    echo "WARNING: $failed run(s) failed"
    exit 1
fi

# Generate comparison summary
python3 "$SCRIPT_DIR/summarise_priority_comparison.py" "$RESULTS_DIR"

echo "All priority comparison runs complete. Results in $RESULTS_DIR/"
