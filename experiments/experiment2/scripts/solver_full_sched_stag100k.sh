#!/bin/bash
exec env RESTART_STAGNATION=100000 ./experiments/experiment2/scripts/solver_full_sched.sh "$1"
