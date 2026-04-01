#!/usr/bin/env python3
"""Generate a comparison summary for experiment 3 (time budget sensitivity)."""

import json
import sys
from pathlib import Path

GA_TIMES = [1, 3, 10, 28]
DATASETS = ["j30", "j60"]


def load_summary(results_dir: Path, ga_time: int, dataset: str) -> dict:
    path = results_dir / f"{ga_time}s_{dataset}" / "summary.json"
    with open(path) as f:
        return json.load(f)


def main():
    results_dir = Path(sys.argv[1])

    rows = []
    for ga_time in GA_TIMES:
        for dataset in DATASETS:
            s = load_summary(results_dir, ga_time, dataset)
            rows.append({
                "ga_time_s": ga_time,
                "dataset": dataset,
                "instances": s["instance_count"],
                "optimal": s["best_known_match_count"],
                "optimal_pct": round(100 * s["best_known_match_count"] / s["instance_count"], 1),
                "mean_gap_pct": round(s["mean_gap_to_best_known_pct"], 2),
                "max_gap_pct": round(s["max_gap_to_best_known_pct"], 2),
                "mean_quality_pct": round(s["mean_quality_vs_best_known_pct"], 2),
            })

    # Write JSON summary
    output_json = results_dir / "comparison.json"
    with open(output_json, "w") as f:
        json.dump(rows, f, indent=2)

    # Write markdown summary
    output_md = results_dir / "comparison.md"
    with open(output_md, "w") as f:
        f.write("# Experiment 3: Time Budget Sensitivity — Results\n\n")

        for dataset in DATASETS:
            dataset_rows = [r for r in rows if r["dataset"] == dataset]
            f.write(f"## {dataset.upper()} ({dataset_rows[0]['instances']} instances)\n\n")
            f.write("| GA Time | Optimal | Optimal % | Mean Gap | Max Gap | Mean Quality |\n")
            f.write("|---------|---------|-----------|----------|---------|--------------|\n")
            for r in dataset_rows:
                f.write(f"| {r['ga_time_s']}s | {r['optimal']} | {r['optimal_pct']}% "
                        f"| {r['mean_gap_pct']}% | {r['max_gap_pct']}% "
                        f"| {r['mean_quality_pct']}% |\n")
            f.write("\n")

    print(f"Wrote {output_json}")
    print(f"Wrote {output_md}")


if __name__ == "__main__":
    main()
