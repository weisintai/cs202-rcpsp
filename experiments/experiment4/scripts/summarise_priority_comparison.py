#!/usr/bin/env python3
"""Generate a comparison summary for experiment 4 (priority rule comparison)."""

import csv
import json
import sys
from pathlib import Path

RULES = ["random", "lft", "mts", "grd", "spt"]
DATASETS = ["j30", "j60"]


def load_summary(results_dir: Path, rule: str, dataset: str) -> dict:
    path = results_dir / f"{rule}_{dataset}" / "summary.json"
    with open(path) as f:
        return json.load(f)


def load_makespans(results_dir: Path, rule: str, dataset: str) -> dict[str, int]:
    """Load per-instance makespans from results.csv."""
    path = results_dir / f"{rule}_{dataset}" / "results.csv"
    makespans = {}
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            makespans[row["instance"]] = int(row["makespan"])
    return makespans


def count_best_per_rule(results_dir: Path, dataset: str) -> dict[str, int]:
    """Count how many times each rule produces the best (lowest) makespan."""
    all_makespans = {}
    for rule in RULES:
        all_makespans[rule] = load_makespans(results_dir, rule, dataset)

    instances = list(all_makespans[RULES[0]].keys())
    counts = {rule: 0 for rule in RULES}

    for inst in instances:
        best_val = min(all_makespans[rule][inst] for rule in RULES)
        for rule in RULES:
            if all_makespans[rule][inst] == best_val:
                counts[rule] += 1

    return counts


def main():
    results_dir = Path(sys.argv[1])

    rows = []
    best_counts = {}

    for dataset in DATASETS:
        best_counts[dataset] = count_best_per_rule(results_dir, dataset)

    for rule in RULES:
        for dataset in DATASETS:
            s = load_summary(results_dir, rule, dataset)
            rows.append({
                "rule": rule,
                "dataset": dataset,
                "instances": s["instance_count"],
                "optimal": s["best_known_match_count"],
                "optimal_pct": round(100 * s["best_known_match_count"] / s["instance_count"], 1),
                "mean_gap_pct": round(s["mean_gap_to_best_known_pct"], 2),
                "max_gap_pct": round(s["max_gap_to_best_known_pct"], 2),
                "mean_quality_pct": round(s["mean_quality_vs_best_known_pct"], 2),
                "times_best": best_counts[dataset][rule],
            })

    # Write JSON summary
    output_json = results_dir / "comparison.json"
    with open(output_json, "w") as f:
        json.dump(rows, f, indent=2)

    # Write markdown summary
    output_md = results_dir / "comparison.md"
    with open(output_md, "w") as f:
        f.write("# Experiment 4: Priority Rule Comparison — Results\n\n")

        for dataset in DATASETS:
            dataset_rows = [r for r in rows if r["dataset"] == dataset]
            f.write(f"## {dataset.upper()} ({dataset_rows[0]['instances']} instances)\n\n")
            f.write("| Rule | Optimal | Optimal % | Mean Gap | Max Gap | Mean Quality | Times Best |\n")
            f.write("|------|---------|-----------|----------|---------|--------------|-----------|\n")
            for r in dataset_rows:
                f.write(f"| {r['rule'].upper()} | {r['optimal']} | {r['optimal_pct']}% "
                        f"| {r['mean_gap_pct']}% | {r['max_gap_pct']}% "
                        f"| {r['mean_quality_pct']}% | {r['times_best']} |\n")
            f.write("\n")

    print(f"Wrote {output_json}")
    print(f"Wrote {output_md}")


if __name__ == "__main__":
    main()
