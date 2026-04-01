#!/usr/bin/env python3
"""Generate a comparison summary for experiment 2 (scaling)."""

import json
import sys
from pathlib import Path

DATASETS = ["j30", "j60", "j90", "j120"]


def load_summary(results_dir: Path, dataset: str) -> dict:
    path = results_dir / dataset / "summary.json"
    with open(path) as f:
        return json.load(f)


def main():
    results_dir = Path(sys.argv[1])

    rows = []
    for dataset in DATASETS:
        s = load_summary(results_dir, dataset)
        rows.append({
            "dataset": dataset,
            "instances": s["instance_count"],
            "optimal": s["best_known_match_count"],
            "optimal_pct": round(100 * s["best_known_match_count"] / s["instance_count"], 1),
            "mean_gap_pct": round(s["mean_gap_to_best_known_pct"], 2),
            "max_gap_pct": round(s["max_gap_to_best_known_pct"], 2),
            "mean_quality_pct": round(s["mean_quality_vs_best_known_pct"], 2),
            "mean_wall_time_s": round(s["mean_wall_time_seconds"], 2),
        })

    # Write JSON summary
    output_json = results_dir / "comparison.json"
    with open(output_json, "w") as f:
        json.dump(rows, f, indent=2)

    # Write markdown summary
    output_md = results_dir / "comparison.md"
    with open(output_md, "w") as f:
        f.write("# Experiment 2: Scaling Across Instance Sizes — Results\n\n")
        f.write("| Dataset | Instances | Optimal | Optimal % | Mean Gap | Max Gap | Mean Quality | Mean Time |\n")
        f.write("|---------|-----------|---------|-----------|----------|---------|--------------|-----------|\n")
        for r in rows:
            f.write(f"| {r['dataset'].upper()} | {r['instances']} | {r['optimal']} "
                    f"| {r['optimal_pct']}% | {r['mean_gap_pct']}% | {r['max_gap_pct']}% "
                    f"| {r['mean_quality_pct']}% | {r['mean_wall_time_s']}s |\n")
        f.write("\n")

    print(f"Wrote {output_json}")
    print(f"Wrote {output_md}")


if __name__ == "__main__":
    main()
