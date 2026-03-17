from __future__ import annotations

import argparse
import json
from pathlib import Path

from rcpsp import HeuristicConfig, parse_sch, solve
from rcpsp.reference import fetch_reference_values


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


def cmd_compare(args: argparse.Namespace) -> int:
    payload = json.loads(Path(args.benchmark_json).read_text())
    rows = payload["results"]
    references = fetch_reference_values(args.dataset)

    exact_cases = 0
    bounded_cases = 0
    unsat_cases = 0
    matched_exact = 0
    feasible_exact = 0
    feasible_bounded = 0
    matched_unsat = 0
    false_infeasible = 0
    unknown_against_known = 0
    better_than_best_known = 0
    matched_best_known_upper = 0
    exact_gap_sum = 0.0
    bounded_upper_ratio_sum = 0.0
    missing_reference: list[str] = []
    false_infeasible_instances: list[str] = []
    unknown_known_instances: list[str] = []
    better_instances: list[str] = []

    for row in rows:
        name = row["instance"]
        reference = references.get(name)
        if reference is None:
            missing_reference.append(name)
            continue

        status = row["status"]
        makespan = row["makespan"]

        if reference.kind == "exact":
            exact_cases += 1
            optimum = reference.upper
            if status == "feasible" and makespan is not None:
                feasible_exact += 1
                if makespan == optimum:
                    matched_exact += 1
                exact_gap_sum += makespan / optimum
            elif status == "infeasible":
                false_infeasible += 1
                false_infeasible_instances.append(name)
            elif status == "unknown":
                unknown_against_known += 1
                unknown_known_instances.append(name)
        elif reference.kind == "bounded":
            bounded_cases += 1
            upper = reference.upper
            if status == "feasible" and makespan is not None:
                feasible_bounded += 1
                bounded_upper_ratio_sum += makespan / upper
                if makespan < upper:
                    better_than_best_known += 1
                    better_instances.append(name)
                elif makespan == upper:
                    matched_best_known_upper += 1
            elif status == "infeasible":
                false_infeasible += 1
                false_infeasible_instances.append(name)
            elif status == "unknown":
                unknown_against_known += 1
                unknown_known_instances.append(name)
        else:
            unsat_cases += 1
            if status == "infeasible":
                matched_unsat += 1

    summary = {
        "dataset": args.dataset,
        "benchmark_json": args.benchmark_json,
        "instances": len(rows),
        "exact_cases": exact_cases,
        "bounded_cases": bounded_cases,
        "unsat_cases": unsat_cases,
        "matched_exact": matched_exact,
        "feasible_exact": feasible_exact,
        "exact_match_rate": matched_exact / exact_cases if exact_cases else 0.0,
        "avg_exact_ratio_to_reference": exact_gap_sum / feasible_exact if feasible_exact else None,
        "feasible_bounded": feasible_bounded,
        "avg_ratio_to_best_known_upper": (
            bounded_upper_ratio_sum / feasible_bounded if feasible_bounded else None
        ),
        "matched_best_known_upper": matched_best_known_upper,
        "better_than_best_known": better_than_best_known,
        "matched_unsat": matched_unsat,
        "unsat_match_rate": matched_unsat / unsat_cases if unsat_cases else 0.0,
        "false_infeasible": false_infeasible,
        "unknown_against_known_reference": unknown_against_known,
        "missing_reference": len(missing_reference),
    }

    details = {
        "false_infeasible_instances": false_infeasible_instances,
        "unknown_known_instances": unknown_known_instances,
        "better_than_best_known_instances": better_instances,
        "missing_reference_instances": missing_reference,
    }
    result = {"summary": summary, "details": details}
    if args.output:
        Path(args.output).write_text(json.dumps(result, indent=2))

    print(json.dumps(result, indent=2))
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

    compare_parser = subparsers.add_parser("compare", help="compare benchmark JSON against reference values")
    compare_parser.add_argument("benchmark_json")
    compare_parser.add_argument("--dataset", choices=("sm_j10", "sm_j20"), required=True)
    compare_parser.add_argument("--output")
    compare_parser.set_defaults(func=cmd_compare)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
