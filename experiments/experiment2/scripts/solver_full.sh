#!/bin/bash
time_budget="${TIME_BUDGET:-3}"
restart_stagnation="${RESTART_STAGNATION:-100000}"
restart_elites="${RESTART_ELITES:-10}"
mutation_rate="${MUTATION_RATE:-0.3}"

exec ./solver "$1" \
  --time "$time_budget" \
  --restart-stagnation "$restart_stagnation" \
  --restart-elites "$restart_elites" \
  --mutation-rate "$mutation_rate" \
  --mode full
