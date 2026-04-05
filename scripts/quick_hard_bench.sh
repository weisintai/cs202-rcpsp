#!/bin/bash
set -euo pipefail

top_k="${1:-5}"
solver="${SOLVER:-./experiments/experiment2/scripts/solver_full.sh}"
timeout="${TIMEOUT:-5}"
output_root="${OUTPUT_ROOT:-benchmark_results/quick_hard_top${top_k}}"

datasets=(j30 j60 j90 j120)

for dataset in "${datasets[@]}"; do
  list_file="benchmark_results/hard_instances/${dataset}_top${top_k}.txt"
  if [[ ! -f "${list_file}" ]]; then
    echo "missing hard-instance list: ${list_file}" >&2
    echo "generate it first with: python3 scripts/derive_hard_instances.py --top-k ${top_k}" >&2
    exit 1
  fi

  echo
  echo "== ${dataset} top${top_k} =="
  python3 scripts/benchmark_rcpsp.py run \
    --dataset "${dataset}" \
    --solver "${solver}" \
    --timeout "${timeout}" \
    --instance-list "${list_file}" \
    --output-dir "${output_root}/${dataset}"
done

echo
echo "wrote quick hard-subset results under ${output_root}/"
