from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from rcpsp import HeuristicConfig, parse_sch, solve, solve_cp, solve_cp_full, solve_sgs
from rcpsp.models import SolveResult
from rcpsp.reference import REFERENCE_URLS, fetch_reference_values, normalize_instance_name

BENCHMARK_DATA_ROOT = Path("benchmarks/data")


def _solve_with_backend(
    instance,
    *,
    backend: str,
    time_limit: float,
    seed: int,
    max_restarts: int | None,
    config: HeuristicConfig | None = None,
):
    config = config or HeuristicConfig(max_restarts=max_restarts)
    if backend == "cp":
        result = solve_cp(instance, time_limit=time_limit, seed=seed, config=config)
    elif backend == "cp_full":
        result = solve_cp_full(instance, time_limit=time_limit, seed=seed, config=config)
    elif backend == "sgs":
        result = solve_sgs(instance, time_limit=time_limit, seed=seed, config=config)
    else:
        result = solve(instance, time_limit=time_limit, seed=seed, config=config)
    return result


def _config_from_args(args: argparse.Namespace) -> HeuristicConfig:
    return HeuristicConfig(
        slack_weight=args.slack_weight,
        tail_weight=args.tail_weight,
        overload_weight=args.overload_weight,
        resource_weight=args.resource_weight,
        late_weight=args.late_weight,
        noise_weight=args.noise_weight,
        max_restarts=args.max_restarts,
    )


def _runtime_tolerance_seconds(time_limit: float) -> float:
    return max(0.01, time_limit * 0.02)


def _enforce_runtime_limit(
    result: SolveResult,
    *,
    time_limit: float,
    observed_runtime_seconds: float | None = None,
    runtime_basis: str = "solver",
) -> SolveResult:
    tolerance = _runtime_tolerance_seconds(time_limit)
    runtime_limit = time_limit + tolerance
    observed_runtime = result.runtime_seconds if observed_runtime_seconds is None else observed_runtime_seconds
    metadata = dict(result.metadata)
    runtime_changed = abs(observed_runtime - result.runtime_seconds) > 1e-12

    if runtime_basis != "solver":
        metadata["runtime_basis"] = runtime_basis
        metadata["solver_runtime_seconds"] = round(result.runtime_seconds, 6)
        metadata[f"{runtime_basis}_runtime_seconds"] = round(observed_runtime, 6)

    if observed_runtime <= runtime_limit:
        if not runtime_changed and metadata == result.metadata:
            return result
        return SolveResult(
            instance_name=result.instance_name,
            status=result.status,
            schedule=result.schedule,
            runtime_seconds=observed_runtime,
            temporal_lower_bound=result.temporal_lower_bound,
            restarts=result.restarts,
            metadata=metadata,
        )

    metadata["original_status"] = result.status
    metadata["late_solution"] = 1
    metadata["runtime_limit_seconds"] = round(runtime_limit, 6)
    metadata["runtime_tolerance_seconds"] = round(tolerance, 6)
    metadata["reason"] = (
        f"{runtime_basis} runtime {observed_runtime:.6f}s exceeded budget {time_limit:.6f}s "
        f"with tolerance {tolerance:.6f}s"
    )
    return SolveResult(
        instance_name=result.instance_name,
        status="unknown",
        schedule=None,
        runtime_seconds=observed_runtime,
        temporal_lower_bound=result.temporal_lower_bound,
        restarts=result.restarts,
        metadata=metadata,
    )


def _resolve_dataset_path(path: Path) -> Path:
    if path.exists():
        return path
    candidate = BENCHMARK_DATA_ROOT / path
    if candidate.exists():
        return candidate
    return path


def _instance_paths(path: Path) -> list[Path]:
    path = _resolve_dataset_path(path)
    if path.is_dir():
        return sorted(
            candidate
            for candidate in path.iterdir()
            if candidate.is_file()
            and candidate.suffix.lower() == ".sch"
            and "copy" not in candidate.name.lower()
        )
    return [path]


def _format_duration(seconds: float) -> str:
    total_seconds = max(0, int(seconds))
    minutes, secs = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0:
        return f"{hours:d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _render_progress(
    *,
    current: int,
    total: int,
    label: str,
    started: float,
    counts: dict[str, int],
    detail: str,
    tty: bool,
) -> None:
    elapsed = time.perf_counter() - started
    average = elapsed / max(1, current)
    eta = average * max(0, total - current)
    if tty:
        width = 24
        filled = width if total == 0 else int(width * current / total)
        bar = "#" * filled + "-" * (width - filled)
        message = (
            f"\r{label} [{bar}] {current}/{total} "
            f"F:{counts['feasible']} I:{counts['infeasible']} U:{counts['unknown']} "
            f"elapsed { _format_duration(elapsed) } eta { _format_duration(eta) } {detail}"
        )
        print(message[:220], end="", file=sys.stderr, flush=True)
        if current == total:
            print(file=sys.stderr, flush=True)
    else:
        print(
            (
                f"[{label}] {current}/{total} "
                f"F:{counts['feasible']} I:{counts['infeasible']} U:{counts['unknown']} "
                f"elapsed {_format_duration(elapsed)} eta {_format_duration(eta)} {detail}"
            ),
            file=sys.stderr,
            flush=True,
        )


def cmd_solve(args: argparse.Namespace) -> int:
    started = time.perf_counter()
    instance = parse_sch(_resolve_dataset_path(Path(args.path)))
    config = _config_from_args(args)
    raw_result = _solve_with_backend(
        instance,
        backend=args.backend,
        time_limit=args.time_limit,
        seed=args.seed,
        max_restarts=config.max_restarts,
        config=config,
    )
    wall_runtime = time.perf_counter() - started
    result = _enforce_runtime_limit(
        raw_result,
        time_limit=args.time_limit,
        observed_runtime_seconds=wall_runtime,
        runtime_basis="wall",
    )
    solver_runtime = float(result.metadata.get("solver_runtime_seconds", raw_result.runtime_seconds))
    payload = {
        "instance": result.instance_name,
        "status": result.status,
        "makespan": result.schedule.makespan if result.schedule is not None else None,
        "temporal_lower_bound": result.temporal_lower_bound,
        "runtime_seconds": round(result.runtime_seconds, 6),
        "solver_runtime_seconds": round(solver_runtime, 6),
        "restarts": result.restarts,
        "start_times": list(result.schedule.start_times) if result.schedule is not None else None,
        "metadata": result.metadata,
        "backend": args.backend,
    }
    if args.json:
        print(json.dumps(payload))
    else:
        print(f"Instance: {payload['instance']}")
        print(f"Status: {payload['status']}")
        print(f"Makespan: {payload['makespan']}")
        print(f"Temporal lower bound: {payload['temporal_lower_bound']}")
        print(f"Wall runtime (s): {payload['runtime_seconds']}")
        print(f"Solver runtime (s): {payload['solver_runtime_seconds']}")
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
    config = _config_from_args(args)
    rows = []
    counts = {"feasible": 0, "infeasible": 0, "unknown": 0}
    over_budget = 0
    started = time.perf_counter()
    tty = sys.stderr.isatty()
    for index, path in enumerate(paths, start=1):
        case_started = time.perf_counter()
        instance = parse_sch(path)
        if args.no_progress and args.time_limit >= 5.0:
            print(
                f"[benchmark] start {index}/{len(paths)} {instance.name}",
                file=sys.stderr,
                flush=True,
            )
        raw_result = _solve_with_backend(
            instance,
            backend=args.backend,
            time_limit=args.time_limit,
            seed=args.seed + index - 1,
            max_restarts=config.max_restarts,
            config=config,
        )
        wall_runtime = time.perf_counter() - case_started
        result = _enforce_runtime_limit(
            raw_result,
            time_limit=args.time_limit,
            observed_runtime_seconds=wall_runtime,
            runtime_basis="wall",
        )
        solver_runtime = float(result.metadata.get("solver_runtime_seconds", raw_result.runtime_seconds))
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
                "solver_runtime_seconds": solver_runtime,
                "restarts": result.restarts,
                "backend": args.backend,
                "metadata": result.metadata,
                "over_budget": int(result.runtime_seconds > args.time_limit + _runtime_tolerance_seconds(args.time_limit)),
            }
        )
        counts[result.status] += 1
        over_budget += rows[-1]["over_budget"]
        if not args.no_progress:
            detail = f"{result.instance_name} {result.status}"
            if result.schedule is not None:
                detail += f" mk={result.schedule.makespan}"
            _render_progress(
                current=index,
                total=len(paths),
                label="benchmark",
                started=started,
                counts=counts,
                detail=detail,
                tty=tty,
            )

    feasible = [row for row in rows if row["status"] == "feasible" and row["ratio"] is not None]
    summary = {
        "backend": args.backend,
        "instances": len(rows),
        "feasible": sum(row["status"] == "feasible" for row in rows),
        "infeasible": sum(row["status"] == "infeasible" for row in rows),
        "unknown": sum(row["status"] == "unknown" for row in rows),
        "avg_makespan": (
            sum(row["makespan"] for row in feasible if row["makespan"] is not None) / max(1, len(feasible))
        ),
        "avg_ratio": sum(row["ratio"] for row in feasible) / max(1, len(feasible)),
        "avg_runtime_seconds": sum(row["runtime_seconds"] for row in rows) / max(1, len(rows)),
        "max_runtime_seconds": max((row["runtime_seconds"] for row in rows), default=0.0),
        "avg_solver_runtime_seconds": sum(row["solver_runtime_seconds"] for row in rows) / max(1, len(rows)),
        "max_solver_runtime_seconds": max((row["solver_runtime_seconds"] for row in rows), default=0.0),
        "best_ratio": min((row["ratio"] for row in feasible), default=0.0),
        "worst_ratio": max((row["ratio"] for row in feasible), default=0.0),
        "over_budget": over_budget,
        "runtime_basis": "wall",
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
    started = time.perf_counter()
    tty = sys.stderr.isatty()

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

    for index, row in enumerate(rows, start=1):
        name = row["instance"]
        normalized_name = normalize_instance_name(name)
        reference = references.get(normalized_name)
        if reference is None:
            missing_reference.append(name)
            if not args.no_progress:
                _render_progress(
                    current=index,
                    total=len(rows),
                    label="compare",
                    started=started,
                    counts={
                        "feasible": feasible_exact + feasible_bounded,
                        "infeasible": false_infeasible + matched_unsat,
                        "unknown": unknown_against_known,
                    },
                    detail=f"{name} missing-ref",
                    tty=tty,
                )
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

        if not args.no_progress:
            _render_progress(
                current=index,
                total=len(rows),
                label="compare",
                started=started,
                counts={
                    "feasible": feasible_exact + feasible_bounded,
                    "infeasible": false_infeasible + matched_unsat,
                    "unknown": unknown_against_known,
                },
                detail=f"{name} {status}",
                tty=tty,
            )

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
    solve_parser.add_argument("--backend", choices=("hybrid", "cp", "cp_full", "sgs"), default="hybrid")
    solve_parser.add_argument("--slack-weight", type=float, default=HeuristicConfig.slack_weight)
    solve_parser.add_argument("--tail-weight", type=float, default=HeuristicConfig.tail_weight)
    solve_parser.add_argument("--overload-weight", type=float, default=HeuristicConfig.overload_weight)
    solve_parser.add_argument("--resource-weight", type=float, default=HeuristicConfig.resource_weight)
    solve_parser.add_argument("--late-weight", type=float, default=HeuristicConfig.late_weight)
    solve_parser.add_argument("--noise-weight", type=float, default=HeuristicConfig.noise_weight)
    solve_parser.add_argument("--json", action="store_true")
    solve_parser.set_defaults(func=cmd_solve)

    bench_parser = subparsers.add_parser("benchmark", help="benchmark a folder or one instance")
    bench_parser.add_argument("path")
    bench_parser.add_argument("--time-limit", type=float, default=0.1)
    bench_parser.add_argument("--seed", type=int, default=0)
    bench_parser.add_argument("--max-restarts", type=int, default=None)
    bench_parser.add_argument("--backend", choices=("hybrid", "cp", "cp_full", "sgs"), default="hybrid")
    bench_parser.add_argument("--slack-weight", type=float, default=HeuristicConfig.slack_weight)
    bench_parser.add_argument("--tail-weight", type=float, default=HeuristicConfig.tail_weight)
    bench_parser.add_argument("--overload-weight", type=float, default=HeuristicConfig.overload_weight)
    bench_parser.add_argument("--resource-weight", type=float, default=HeuristicConfig.resource_weight)
    bench_parser.add_argument("--late-weight", type=float, default=HeuristicConfig.late_weight)
    bench_parser.add_argument("--noise-weight", type=float, default=HeuristicConfig.noise_weight)
    bench_parser.add_argument("--output")
    bench_parser.add_argument("--no-progress", action="store_true")
    bench_parser.set_defaults(func=cmd_benchmark)

    compare_parser = subparsers.add_parser("compare", help="compare benchmark JSON against reference values")
    compare_parser.add_argument("benchmark_json")
    compare_parser.add_argument("--dataset", choices=tuple(sorted(REFERENCE_URLS)), required=True)
    compare_parser.add_argument("--output")
    compare_parser.add_argument("--no-progress", action="store_true")
    compare_parser.set_defaults(func=cmd_compare)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
