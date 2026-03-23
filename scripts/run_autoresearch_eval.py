from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.autoresearch_lib import compare_summaries, summarize_autoresearch
from scripts.guardrails_lib import PRESETS, run_guardrail_suite


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the RCPSP autoresearch evaluation loop.")
    parser.add_argument("--backend", choices=("hybrid", "cp"), default="cp")
    parser.add_argument("--preset", choices=tuple(PRESETS), default="submission_quick")
    parser.add_argument("--datasets", nargs="*", help="optional subset of datasets from the selected preset")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-restarts", type=int, default=None)
    parser.add_argument("--slack-weight", type=float, default=None)
    parser.add_argument("--tail-weight", type=float, default=None)
    parser.add_argument("--overload-weight", type=float, default=None)
    parser.add_argument("--resource-weight", type=float, default=None)
    parser.add_argument("--late-weight", type=float, default=None)
    parser.add_argument("--noise-weight", type=float, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--baseline", type=Path, default=None, help="optional prior autoresearch_eval.json to compare against")
    parser.add_argument("--require-improvement", action="store_true", help="exit non-zero if the score does not improve over --baseline")
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
        seed=args.seed,
        max_restarts=args.max_restarts,
        heuristic_args=heuristic_args,
        output_dir=args.output_dir,
        dry_run=args.dry_run,
    )
    payload = {
        "backend": args.backend,
        "preset": args.preset,
        "seed": args.seed,
        "max_restarts": args.max_restarts,
        "heuristic_args": heuristic_args,
        "output_dir": result["output_dir"],
        "guardrail_summary_path": result["summary_path"],
    }

    comparison = None
    if args.dry_run:
        payload["evaluation"] = None
    else:
        evaluation = summarize_autoresearch(result["summary"])
        payload["evaluation"] = evaluation
        if args.baseline is not None:
            baseline_payload = json.loads(args.baseline.read_text(encoding="utf-8"))
            comparison = compare_summaries(evaluation, baseline_payload["evaluation"])
            payload["comparison_to_baseline"] = comparison

        output_path = Path(result["output_dir"]) / "autoresearch_eval.json"
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        payload["evaluation_path"] = str(output_path)

    print(json.dumps(payload, indent=2))
    if args.require_improvement and comparison is not None and not comparison["better"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
