from __future__ import annotations

import argparse
from pathlib import Path

from scripts.guardrails_lib import PRESETS, run_guardrail_suite


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the SGS guardrail benchmark suite.")
    parser.add_argument("--preset", choices=tuple(PRESETS), default="full")
    parser.add_argument("--datasets", nargs="*", help="optional subset of datasets from the selected preset")
    parser.add_argument("--jobs", type=int, default=1, help="number of datasets to run concurrently; use 0 to run all selected datasets in parallel")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-restarts", type=int, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_guardrail_suite(
        backend="sgs",
        preset=args.preset,
        datasets=args.datasets,
        jobs=args.jobs,
        seed=args.seed,
        max_restarts=args.max_restarts,
        output_dir=args.output_dir,
        dry_run=args.dry_run,
    )
    if not args.dry_run and result["summary_path"] is not None:
        print(f"wrote {result['summary_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
