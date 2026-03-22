from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rcpsp import HeuristicConfig, parse_sch, solve_cp
from rcpsp.models import SolveResult
from rcpsp.reference import ReferenceValue, fetch_reference_values, normalize_instance_name

BENCHMARK_DATA_ROOT = ROOT / "benchmarks" / "data"
HELDOUT_DATA_ROOT = ROOT / "references" / "kobe-scheduling" / "data" / "rcpsp-max"


def runtime_tolerance_seconds(time_limit: float) -> float:
    return max(0.01, time_limit * 0.02)


def enforce_runtime_limit(result: SolveResult, *, time_limit: float) -> SolveResult:
    runtime_limit = time_limit + runtime_tolerance_seconds(time_limit)
    if result.runtime_seconds <= runtime_limit:
        return result

    metadata = dict(result.metadata)
    metadata["original_status"] = result.status
    metadata["late_solution"] = 1
    metadata["runtime_limit_seconds"] = round(runtime_limit, 6)
    metadata["runtime_tolerance_seconds"] = round(runtime_tolerance_seconds(time_limit), 6)
    metadata["reason"] = (
        f"runtime {result.runtime_seconds:.6f}s exceeded budget {time_limit:.6f}s "
        f"with tolerance {runtime_tolerance_seconds(time_limit):.6f}s"
    )
    return SolveResult(
        instance_name=result.instance_name,
        status="unknown",
        schedule=None,
        runtime_seconds=result.runtime_seconds,
        temporal_lower_bound=result.temporal_lower_bound,
        restarts=result.restarts,
        metadata=metadata,
    )


def resolve_dataset_dir(dataset: str) -> Path:
    candidates = [
        Path(dataset),
        BENCHMARK_DATA_ROOT / dataset,
        HELDOUT_DATA_ROOT / dataset,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    joined = ", ".join(str(candidate) for candidate in candidates)
    raise FileNotFoundError(f"could not resolve dataset {dataset!r}; tried: {joined}")


def index_instance_paths(dataset_dir: Path) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for path in sorted(dataset_dir.iterdir()):
        if not path.is_file() or path.suffix.lower() != ".sch":
            continue
        paths[normalize_instance_name(path.stem)] = path
        paths[normalize_instance_name(path.name)] = path
    return paths


def classify_miss(row: dict[str, object], reference: ReferenceValue) -> str | None:
    status = str(row["status"])
    makespan = row.get("makespan")
    if reference.kind == "exact":
        if status == "feasible" and makespan is not None and int(makespan) != int(reference.upper):
            return "exact_suboptimal"
        if status == "unknown":
            return "exact_unknown"
        if status == "infeasible":
            return "exact_false_infeasible"
        return None
    if reference.kind == "bounded":
        if status != "feasible":
            return "bounded_no_feasible"
        return None
    if status != "infeasible":
        return "unsat_miss"
    return None


def analyze_case(
    *,
    row: dict[str, object],
    miss_kind: str,
    reference: ReferenceValue,
    instance_path: Path,
    time_limit: float,
    seed: int,
) -> dict[str, object]:
    instance = parse_sch(instance_path)
    result = enforce_runtime_limit(
        solve_cp(instance, time_limit=time_limit, seed=seed, config=HeuristicConfig()),
        time_limit=time_limit,
    )
    metadata = dict(result.metadata)
    return {
        "instance": row["instance"],
        "path": str(instance_path),
        "miss_kind": miss_kind,
        "reference_kind": reference.kind,
        "reference_lower": reference.lower,
        "reference_upper": reference.upper,
        "original_status": row["status"],
        "original_makespan": row.get("makespan"),
        "original_runtime_seconds": row.get("runtime_seconds"),
        "rerun_status": result.status,
        "rerun_makespan": result.schedule.makespan if result.schedule is not None else None,
        "rerun_runtime_seconds": result.runtime_seconds,
        "restarts": result.restarts,
        "seed": seed,
        "seed_best_source": metadata.get("seed_best_source", "missing"),
        "incumbent_updates": metadata.get("incumbent_updates", 0),
        "search_nodes": metadata.get("search_nodes", 0),
        "conflict_events": metadata.get("conflict_events", 0),
        "avg_conflict_size": metadata.get("avg_conflict_size", 0.0),
        "propagation_calls": metadata.get("propagation_calls", 0),
        "propagation_rounds": metadata.get("propagation_rounds", 0),
        "late_solution": int(bool(metadata.get("late_solution", 0))),
        "reason": metadata.get("reason"),
        "metadata": metadata,
    }


def summarize_cases(cases: list[dict[str, object]]) -> dict[str, object]:
    seed_sources = Counter(str(case["seed_best_source"]) for case in cases)
    miss_kinds = Counter(str(case["miss_kind"]) for case in cases)
    rerun_statuses = Counter(str(case["rerun_status"]) for case in cases)
    if not cases:
        return {
            "cases": 0,
            "miss_kinds": {},
            "seed_best_source": {},
            "rerun_statuses": {},
        }

    def average(field: str) -> float:
        values = [float(case[field]) for case in cases]
        return sum(values) / len(values)

    return {
        "cases": len(cases),
        "miss_kinds": dict(sorted(miss_kinds.items())),
        "seed_best_source": dict(sorted(seed_sources.items())),
        "rerun_statuses": dict(sorted(rerun_statuses.items())),
        "avg_incumbent_updates": average("incumbent_updates"),
        "avg_search_nodes": average("search_nodes"),
        "avg_conflict_events": average("conflict_events"),
        "avg_conflict_size": average("avg_conflict_size"),
        "avg_propagation_calls": average("propagation_calls"),
        "avg_propagation_rounds": average("propagation_rounds"),
        "avg_runtime_seconds": average("rerun_runtime_seconds"),
        "late_solution_count": sum(int(case["late_solution"]) for case in cases),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze CP miss patterns by rerunning known-reference misses.")
    parser.add_argument("benchmark_json")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--time-limit", type=float, required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-cases", type=int, default=None)
    parser.add_argument("--output")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    payload = json.loads(Path(args.benchmark_json).read_text())
    rows = payload["results"]
    references = fetch_reference_values(args.dataset)
    dataset_dir = resolve_dataset_dir(args.dataset)
    paths = index_instance_paths(dataset_dir)

    analyses: list[dict[str, object]] = []
    missing_paths: list[str] = []

    for index, row in enumerate(rows):
        name = str(row["instance"])
        reference = references.get(normalize_instance_name(name))
        if reference is None:
            continue
        miss_kind = classify_miss(row, reference)
        if miss_kind is None:
            continue
        instance_path = paths.get(normalize_instance_name(name))
        if instance_path is None:
            missing_paths.append(name)
            continue
        analyses.append(
            analyze_case(
                row=row,
                miss_kind=miss_kind,
                reference=reference,
                instance_path=instance_path,
                time_limit=args.time_limit,
                seed=args.seed + index,
            )
        )
        if args.max_cases is not None and len(analyses) >= args.max_cases:
            break

    result = {
        "dataset": args.dataset,
        "benchmark_json": str(Path(args.benchmark_json).resolve()),
        "dataset_dir": str(dataset_dir.resolve()),
        "time_limit": args.time_limit,
        "cases": analyses,
        "summary": summarize_cases(analyses),
        "missing_paths": missing_paths,
    }

    if args.output:
        Path(args.output).write_text(json.dumps(result, indent=2))

    print(json.dumps(result["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
