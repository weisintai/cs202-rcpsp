from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sweep a solver configuration across multiple time limits.")
    parser.add_argument("--dataset", default="sm_j20")
    parser.add_argument("--dataset-path", default="sm_j20")
    parser.add_argument("--backend", choices=("hybrid", "cp"), default="hybrid")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "tmp" / "time-sweep")
    parser.add_argument("--time-limits", nargs="+", type=float, required=True)
    parser.add_argument("--max-restarts", type=int, default=None)
    parser.add_argument("--slack-weight", type=float, default=None)
    parser.add_argument("--tail-weight", type=float, default=None)
    parser.add_argument("--overload-weight", type=float, default=None)
    parser.add_argument("--resource-weight", type=float, default=None)
    parser.add_argument("--late-weight", type=float, default=None)
    parser.add_argument("--noise-weight", type=float, default=None)
    return parser.parse_args()


def format_budget_label(value: float) -> str:
    if float(value).is_integer():
        return f"{int(value)}s"
    return f"{str(value).replace('.', 'p')}s"


def run_command(args: list[str], log_path: Path) -> None:
    completed = subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        stdout=log_path.open("w", encoding="utf-8"),
        stderr=subprocess.STDOUT,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"command failed ({completed.returncode}): {' '.join(args)}")


def metric_ratio(exact_match_rate: float | None, avg_runtime_seconds: float | None) -> float:
    if exact_match_rate is None or avg_runtime_seconds is None or avg_runtime_seconds <= 0.0:
        return 0.0
    return exact_match_rate / avg_runtime_seconds


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir
    logs_dir = output_dir / "logs"
    output_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    heuristic_args = []
    for flag, value in (
        ("--max-restarts", args.max_restarts),
        ("--slack-weight", args.slack_weight),
        ("--tail-weight", args.tail_weight),
        ("--overload-weight", args.overload_weight),
        ("--resource-weight", args.resource_weight),
        ("--late-weight", args.late_weight),
        ("--noise-weight", args.noise_weight),
    ):
        if value is not None:
            heuristic_args.extend([flag, str(value)])

    rows: list[dict] = []
    for time_limit in args.time_limits:
        label = format_budget_label(time_limit)
        benchmark_path = output_dir / f"{args.dataset}_{label}_{args.backend}_benchmark.json"
        compare_path = output_dir / f"{args.dataset}_{label}_{args.backend}_compare.json"

        benchmark_cmd = [
            sys.executable,
            "main.py",
            "benchmark",
            args.dataset_path,
            "--time-limit",
            str(time_limit),
            "--backend",
            args.backend,
            "--seed",
            str(args.seed),
            "--output",
            str(benchmark_path),
            *heuristic_args,
        ]
        compare_cmd = [
            sys.executable,
            "main.py",
            "compare",
            str(benchmark_path),
            "--dataset",
            args.dataset,
            "--output",
            str(compare_path),
        ]

        run_command(benchmark_cmd, logs_dir / f"{args.dataset}_{label}_{args.backend}_benchmark.log")
        run_command(compare_cmd, logs_dir / f"{args.dataset}_{label}_{args.backend}_compare.log")

        benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))["summary"]
        compare = json.loads(compare_path.read_text(encoding="utf-8"))["summary"]
        rows.append(
            {
                "time_limit_seconds": time_limit,
                "matched_exact": compare["matched_exact"],
                "feasible_exact": compare["feasible_exact"],
                "exact_match_rate": compare["exact_match_rate"],
                "avg_exact_ratio_to_reference": compare["avg_exact_ratio_to_reference"],
                "unknown": benchmark["unknown"],
                "over_budget": benchmark["over_budget"],
                "avg_runtime_seconds": benchmark["avg_runtime_seconds"],
                "max_runtime_seconds": benchmark["max_runtime_seconds"],
                "accuracy_per_avg_runtime": metric_ratio(
                    compare.get("exact_match_rate"),
                    benchmark.get("avg_runtime_seconds"),
                ),
            }
        )

    best = max(rows, key=lambda row: float(row["accuracy_per_avg_runtime"]))
    summary = {
        "dataset": args.dataset,
        "dataset_path": args.dataset_path,
        "backend": args.backend,
        "seed": args.seed,
        "config": {
            "max_restarts": args.max_restarts,
            "slack_weight": args.slack_weight,
            "tail_weight": args.tail_weight,
            "overload_weight": args.overload_weight,
            "resource_weight": args.resource_weight,
            "late_weight": args.late_weight,
            "noise_weight": args.noise_weight,
        },
        "rows": rows,
        "best_by_accuracy_per_avg_runtime": best,
    }
    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({"summary_path": str(summary_path), "best": best}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
