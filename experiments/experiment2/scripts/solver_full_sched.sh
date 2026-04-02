#!/bin/bash

# Internal benchmarking wrapper: compare search quality under a fixed schedule
# generation budget rather than wall-clock only.
#
# Override the budget per run with:
#   SCHEDULE_BUDGET=800000 ./experiments/experiment2/scripts/solver_full_sched.sh <instance>
# Optional GA tuning overrides:
#   RESTART_STAGNATION=100000 RESTART_ELITES=10 MUTATION_RATE=0.3 \
#     ./experiments/experiment2/scripts/solver_full_sched.sh <instance>

budget="${SCHEDULE_BUDGET:-1000000}"
restart_stagnation="${RESTART_STAGNATION:-100000}"
restart_elites="${RESTART_ELITES:-10}"
mutation_rate="${MUTATION_RATE:-0.3}"

exec ./solver "$1" \
  --time 999 \
  --schedules "$budget" \
  --restart-stagnation "$restart_stagnation" \
  --restart-elites "$restart_elites" \
  --mutation-rate "$mutation_rate" \
  --mode full
