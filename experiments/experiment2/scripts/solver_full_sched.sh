#!/bin/bash

# Internal benchmarking wrapper: compare search quality under a fixed schedule
# generation budget rather than wall-clock only.
#
# Override the budget per run with:
#   SCHEDULE_BUDGET=800000 ./experiments/experiment2/scripts/solver_full_sched.sh <instance>

budget="${SCHEDULE_BUDGET:-1000000}"
exec ./solver "$1" --time 999 --schedules "$budget" --mode full
