from __future__ import annotations

import argparse
import json
from pathlib import Path

from rcpsp import HeuristicConfig, parse_sch, solve


def _instance_paths(path: Path) -> list[Path]:
    if path.is_dir():
        return sorted(
            candidate
            for candidate in path.glob("PSP*.SCH")
            if candidate.is_file() and "copy" not in candidate.name
        )
    return [path]


def cmd_solve(args: argparse.Namespace) -> int:
    instance = parse_sch(args.path)
    result = solve(
        instance,
        time_limit=args.time_limit,
        seed=args.seed,
        config=HeuristicConfig(max_restarts=args.max_restarts),
    )
    payload = {
        "instance": result.instance_name,
        "status": result.status,
        "makespan": result.schedule.makespan if result.schedule is not None else None,
        "temporal_lower_bound": result.temporal_lower_bound,
        "runtime_seconds": round(result.runtime_seconds, 6),
        "restarts": result.restarts,
        "start_times": list(result.schedule.start_times) if result.schedule is not None else None,
        "metadata": result.metadata,
    }
    if args.json:
        print(json.dumps(payload))
    else:
        print(f"Instance: {payload['instance']}")
        print(f"Status: {payload['status']}")
        print(f"Makespan: {payload['makespan']}")
        print(f"Temporal lower bound: {payload['temporal_lower_bound']}")
        print(f"Runtime (s): {payload['runtime_seconds']}")
        print(f"Restarts: {payload['restarts']}")
        if payload["start_times"] is not None:
            print("Start times:")
            print(" ".join(str(value) for value in payload["start_times"]))
        if payload["metadata"]:
            print("Metadata:")
            print(json.dumps(payload["metadata"]))
    return 0


def cmd_benchmark(args: argparse.Namespace) -> int:
    paths = _instance_paths(Path(args.path))
    rows = []
    for index, path in enumerate(paths, start=1):
        instance = parse_sch(path)
        result = solve(
            instance,
            time_limit=args.time_limit,
            seed=args.seed + index - 1,
            config=HeuristicConfig(max_restarts=args.max_restarts),
        )
        rows.append(
            {
                "instance": result.instance_name,
                "status": result.status,
                "makespan": result.schedule.makespan if result.schedule is not None else None,
                "temporal_lower_bound": result.temporal_lower_bound,
                "ratio": (
                    result.schedule.makespan / max(1, result.temporal_lower_bound)
                    if result.schedule is not None and result.temporal_lower_bound > 0
                    else None
                ),
                "runtime_seconds": result.runtime_seconds,
                "restarts": result.restarts,
            }
        )

    feasible = [row for row in rows if row["status"] == "feasible" and row["ratio"] is not None]
    summary = {
        "instances": len(rows),
        "feasible": sum(row["status"] == "feasible" for row in rows),
        "infeasible": sum(row["status"] == "infeasible" for row in rows),
        "unknown": sum(row["status"] == "unknown" for row in rows),
        "avg_makespan": (
            sum(row["makespan"] for row in feasible if row["makespan"] is not None) / max(1, len(feasible))
        ),
        "avg_ratio": sum(row["ratio"] for row in feasible) / max(1, len(feasible)),
        "avg_runtime_seconds": sum(row["runtime_seconds"] for row in rows) / max(1, len(rows)),
        "best_ratio": min((row["ratio"] for row in feasible), default=0.0),
        "worst_ratio": max((row["ratio"] for row in feasible), default=0.0),
    }

    payload = {"summary": summary, "results": rows}
    if args.output:
        Path(args.output).write_text(json.dumps(payload, indent=2))

    print(json.dumps(summary, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="RCPSP/max heuristic solver")
    subparsers = parser.add_subparsers(dest="command", required=True)

    solve_parser = subparsers.add_parser("solve", help="solve one instance")
    solve_parser.add_argument("path")
    solve_parser.add_argument("--time-limit", type=float, default=1.0)
    solve_parser.add_argument("--seed", type=int, default=0)
    solve_parser.add_argument("--max-restarts", type=int, default=None)
    solve_parser.add_argument("--json", action="store_true")
    solve_parser.set_defaults(func=cmd_solve)

    bench_parser = subparsers.add_parser("benchmark", help="benchmark a folder or one instance")
    bench_parser.add_argument("path")
    bench_parser.add_argument("--time-limit", type=float, default=0.1)
    bench_parser.add_argument("--seed", type=int, default=0)
    bench_parser.add_argument("--max-restarts", type=int, default=None)
    bench_parser.add_argument("--output")
    bench_parser.set_defaults(func=cmd_benchmark)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
