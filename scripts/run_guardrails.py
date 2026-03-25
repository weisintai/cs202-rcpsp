from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.guardrails_lib import PRESETS, run_guardrail_suite


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the standard benchmark guardrail suite.")
    parser.add_argument("--backend", choices=("hybrid", "cp", "cp_full", "sgs"), default="cp")
    parser.add_argument("--preset", choices=tuple(PRESETS), default="submission_quick")
    parser.add_argument("--datasets", nargs="*", help="optional subset of datasets from the selected preset")
    parser.add_argument("--jobs", type=int, default=1, help="number of datasets to run concurrently; use 0 to run all selected datasets in parallel")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-restarts", type=int, default=None)
    parser.add_argument("--slack-weight", type=float, default=None)
    parser.add_argument("--tail-weight", type=float, default=None)
    parser.add_argument("--overload-weight", type=float, default=None)
    parser.add_argument("--resource-weight", type=float, default=None)
    parser.add_argument("--late-weight", type=float, default=None)
    parser.add_argument("--noise-weight", type=float, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    heuristic_args = {
        key: value
        for key, value in {
            "slack_weight": args.slack_weight,
            "tail_weight": args.tail_weight,
            "overload_weight": args.overload_weight,
            "resource_weight": args.resource_weight,
            "late_weight": args.late_weight,
            "noise_weight": args.noise_weight,
        }.items()
        if value is not None
    }
    result = run_guardrail_suite(
        backend=args.backend,
        preset=args.preset,
        datasets=args.datasets,
        jobs=args.jobs,
        seed=args.seed,
        max_restarts=args.max_restarts,
        heuristic_args=heuristic_args,
        output_dir=args.output_dir,
        dry_run=args.dry_run,
    )
    if not args.dry_run and result["summary_path"] is not None:
        print(f"wrote {result['summary_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
