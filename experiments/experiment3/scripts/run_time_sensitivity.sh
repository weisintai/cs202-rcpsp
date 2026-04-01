#!/bin/bash
# Experiment 3: Time Budget Sensitivity
# Runs full pipeline at 1s, 3s, 10s, 28s GA budgets on J30 and J60
# All 8 runs launch in parallel

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
RESULTS_DIR="$SCRIPT_DIR/../results"
BENCHMARK="$PROJECT_DIR/scripts/benchmark_rcpsp.py"

cd "$PROJECT_DIR"

# Build solver
make

# Launch all 8 runs in parallel
pids=()

for ga_time in 1 3 10 28; do
    timeout=$((ga_time + 2))
    for dataset in j30 j60; do
        outdir="$RESULTS_DIR/${ga_time}s_${dataset}"
        echo "Launching: ga_time=${ga_time}s dataset=$dataset timeout=${timeout}s"
        python3 "$BENCHMARK" run \
            --dataset "$dataset" \
            --solver "$SCRIPT_DIR/solver_${ga_time}s.sh" \
            --timeout "$timeout" \
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
python3 "$SCRIPT_DIR/summarise_time_sensitivity.py" "$RESULTS_DIR"

echo "All time sensitivity runs complete. Results in $RESULTS_DIR/"
