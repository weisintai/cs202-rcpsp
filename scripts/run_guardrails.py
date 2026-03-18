from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = ROOT / "tmp" / "guardrails"


@dataclass(frozen=True)
class GuardrailCase:
    dataset: str
    time_limit: float


PRESETS: dict[str, tuple[GuardrailCase, ...]] = {
    "quick": (
        GuardrailCase("sm_j10", 0.1),
        GuardrailCase("sm_j20", 0.1),
        GuardrailCase("sm_j30", 0.1),
        GuardrailCase("testset_ubo50", 0.1),
    ),
    "medium": (
        GuardrailCase("sm_j10", 1.0),
        GuardrailCase("sm_j20", 1.0),
    ),
    "full": (
        GuardrailCase("sm_j10", 0.1),
        GuardrailCase("sm_j20", 0.1),
        GuardrailCase("sm_j30", 0.1),
        GuardrailCase("testset_ubo50", 0.1),
        GuardrailCase("sm_j10", 1.0),
        GuardrailCase("sm_j20", 1.0),
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the standard benchmark guardrail suite.")
    parser.add_argument("--backend", choices=("hybrid", "cp"), default="hybrid")
    parser.add_argument("--preset", choices=tuple(PRESETS), default="full")
    parser.add_argument("--datasets", nargs="*", help="optional subset of datasets from the selected preset")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-restarts", type=int, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def format_limit(value: float) -> str:
    return str(value).replace(".", "p")


def run_json_command(command: list[str], *, dry_run: bool) -> dict:
    print(f"$ {' '.join(command)}", flush=True)
    if dry_run:
        return {}
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=None,
        check=True,
    )
    return json.loads(completed.stdout)


def filtered_cases(args: argparse.Namespace) -> list[GuardrailCase]:
    cases = list(PRESETS[args.preset])
    if not args.datasets:
        return cases
    allowed = set(args.datasets)
    return [case for case in cases if case.dataset in allowed]


def build_output_dir(args: argparse.Namespace) -> Path:
    if args.output_dir is not None:
        return args.output_dir
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return DEFAULT_OUTPUT_ROOT / f"{args.backend}-{args.preset}-{timestamp}"


def main() -> int:
    args = parse_args()
    cases = filtered_cases(args)
    if not cases:
        raise SystemExit("No guardrail cases selected.")

    output_dir = build_output_dir(args)
    if not args.dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)

    aggregate: list[dict] = []
    for case in cases:
        label = f"{case.dataset}@{case.time_limit:.1f}s"
        bench_output = output_dir / f"{case.dataset}_{format_limit(case.time_limit)}_{args.backend}_benchmark.json"
        compare_output = output_dir / f"{case.dataset}_{format_limit(case.time_limit)}_{args.backend}_compare.json"

        benchmark_command = [
            sys.executable,
            "main.py",
            "benchmark",
            case.dataset,
            "--time-limit",
            str(case.time_limit),
            "--backend",
            args.backend,
            "--seed",
            str(args.seed),
            "--output",
            str(bench_output),
        ]
        if args.max_restarts is not None:
            benchmark_command.extend(["--max-restarts", str(args.max_restarts)])

        benchmark_summary = run_json_command(benchmark_command, dry_run=args.dry_run)

        compare_command = [
            sys.executable,
            "main.py",
            "compare",
            str(bench_output),
            "--dataset",
            case.dataset,
            "--output",
            str(compare_output),
        ]
        compare_payload = run_json_command(compare_command, dry_run=args.dry_run)
        compare_summary = compare_payload.get("summary", {}) if compare_payload else {}

        aggregate.append(
            {
                "label": label,
                "dataset": case.dataset,
                "time_limit": case.time_limit,
                "benchmark_summary": benchmark_summary,
                "compare_summary": compare_summary,
                "benchmark_output": str(bench_output),
                "compare_output": str(compare_output),
            }
        )

        if args.dry_run:
            continue

        print(
            (
                f"{label}: "
                f"F={benchmark_summary['feasible']} "
                f"I={benchmark_summary['infeasible']} "
                f"U={benchmark_summary['unknown']} "
                f"exact={compare_summary.get('matched_exact', 0)}/{compare_summary.get('exact_cases', 0)} "
                f"rate={compare_summary.get('exact_match_rate', 0.0):.3f}"
            ),
            flush=True,
        )

    if args.dry_run:
        return 0

    combined_path = output_dir / "summary.json"
    combined_path.write_text(json.dumps({"backend": args.backend, "preset": args.preset, "runs": aggregate}, indent=2))
    print(f"wrote {combined_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
