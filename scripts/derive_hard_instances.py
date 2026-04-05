#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "benchmark_results" / "hard_instances"
EXPECTED_INSTANCE_COUNTS = {
    "j30": 480,
    "j60": 480,
    "j90": 480,
    "j120": 600,
}

# Keep the aggregation focused on comparable "real" full-pipeline ~3s runs.
EXCLUDED_PATH_PARTS = (
    "smoke",
    "experiment1/results/baseline_",
    "experiment1/results/priority_",
    "experiment1/results/ga_",
    "experiment4/results/",
    "schedule_budget",
    "10s_",
    "1s_",
    "28s_",
    "restart_tuning_10s",
    "1m",
    "regressions",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Derive stable hard-instance subsets from historical benchmark CSVs."
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=20,
        help="Number of hard instances to emit per dataset.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for generated hard-instance lists.",
    )
    return parser.parse_args()


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows or "dataset" not in rows[0]:
        return []
    return rows


def mean_wall_time(rows: list[dict[str, str]]) -> float:
    times = [float(row["wall_time_seconds"]) for row in rows if row["status"] == "ok"]
    return sum(times) / len(times)


def discover_comparable_runs(dataset: str) -> list[Path]:
    expected_count = EXPECTED_INSTANCE_COUNTS[dataset]
    matches: list[Path] = []

    for path in sorted(ROOT.glob("**/results.csv")):
        path_str = str(path.relative_to(ROOT))
        if dataset not in path_str:
            continue
        if any(part in path_str for part in EXCLUDED_PATH_PARTS):
            continue

        rows = [row for row in read_rows(path) if row["dataset"] == dataset]
        if len(rows) != expected_count:
            continue
        if len({row["file"] for row in rows}) != expected_count:
            continue

        avg_time = mean_wall_time(rows)
        if 2.5 <= avg_time <= 3.5:
            matches.append(path)

    return matches


def score_instance(gaps: list[float], matched_count: int) -> tuple[float, float, float, float]:
    run_count = len(gaps)
    mean_gap = sum(gaps) / run_count
    max_gap = max(gaps)
    miss_rate = 1.0 - (matched_count / run_count)
    score = mean_gap + 0.5 * max_gap + 10.0 * miss_rate
    return score, mean_gap, miss_rate, max_gap


def aggregate_dataset(dataset: str, run_paths: list[Path]) -> list[dict[str, object]]:
    per_instance: dict[str, dict[str, object]] = defaultdict(
        lambda: {"gaps": [], "matched_count": 0}
    )

    for path in run_paths:
        for row in read_rows(path):
            if row["dataset"] != dataset or row["status"] != "ok":
                continue
            gap = row["gap_to_best_known_pct"]
            if gap == "":
                continue

            record = per_instance[row["file"]]
            record["gaps"].append(float(gap))
            if row["matched_best_known"] == "True":
                record["matched_count"] += 1

    ranked: list[dict[str, object]] = []
    for file_path, record in per_instance.items():
        gaps = record["gaps"]
        matched_count = int(record["matched_count"])
        score, mean_gap, miss_rate, max_gap = score_instance(gaps, matched_count)
        ranked.append(
            {
                "file": file_path,
                "basename": Path(file_path).name,
                "score": score,
                "mean_gap_pct": mean_gap,
                "miss_rate": miss_rate,
                "max_gap_pct": max_gap,
                "run_count": len(gaps),
            }
        )

    ranked.sort(key=lambda row: (row["score"], row["mean_gap_pct"], row["max_gap_pct"]), reverse=True)
    return ranked


def write_outputs(
    dataset: str,
    ranked: list[dict[str, object]],
    run_paths: list[Path],
    top_k: int,
    output_dir: Path,
) -> dict[str, object]:
    selected = ranked[:top_k]

    txt_path = output_dir / f"{dataset}_top{top_k}.txt"
    txt_path.write_text(
        "".join(f"{row['basename']}\n" for row in selected),
        encoding="utf-8",
    )

    csv_path = output_dir / f"{dataset}_top{top_k}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "rank",
                "basename",
                "file",
                "score",
                "mean_gap_pct",
                "miss_rate",
                "max_gap_pct",
                "run_count",
            ]
        )
        for rank, row in enumerate(selected, start=1):
            writer.writerow(
                [
                    rank,
                    row["basename"],
                    row["file"],
                    f"{row['score']:.6f}",
                    f"{row['mean_gap_pct']:.6f}",
                    f"{row['miss_rate']:.6f}",
                    f"{row['max_gap_pct']:.6f}",
                    row["run_count"],
                ]
            )

    return {
        "dataset": dataset,
        "top_k": top_k,
        "selected_run_count": len(run_paths),
        "selected_runs": [str(path.relative_to(ROOT)) for path in run_paths],
        "txt": str(txt_path.relative_to(ROOT)),
        "csv": str(csv_path.relative_to(ROOT)),
    }


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    summary: dict[str, object] = {
        "method": {
            "description": "Rank instances by repeated difficulty on comparable ~3s full-dataset runs.",
            "score": "mean_gap_pct + 0.5 * max_gap_pct + 10 * miss_rate",
            "excluded_path_parts": list(EXCLUDED_PATH_PARTS),
            "top_k": args.top_k,
        },
        "datasets": {},
    }

    for dataset in EXPECTED_INSTANCE_COUNTS:
        run_paths = discover_comparable_runs(dataset)
        ranked = aggregate_dataset(dataset, run_paths)
        summary["datasets"][dataset] = write_outputs(
            dataset=dataset,
            ranked=ranked,
            run_paths=run_paths,
            top_k=args.top_k,
            output_dir=args.output_dir,
        )

    summary_path = args.output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"Wrote hard-instance lists to {args.output_dir}")
    for dataset in EXPECTED_INSTANCE_COUNTS:
        dataset_summary = summary["datasets"][dataset]
        print(
            f"{dataset}: "
            f"{dataset_summary['selected_run_count']} runs -> "
            f"{dataset_summary['txt']}, {dataset_summary['csv']}"
        )
    print(f"summary: {summary_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
