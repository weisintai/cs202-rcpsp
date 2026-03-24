from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


CASE_SETS: dict[str, tuple[str, ...]] = {
    "public_30_residue": (
        "sm_j30/PSP37.SCH",
        "sm_j30/PSP46.SCH",
        "testset_ubo50/psp4.sch",
        "testset_ubo50/psp9.sch",
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a small CP residue set for fast solver iteration."
    )
    parser.add_argument("--time-limit", type=float, default=30.0)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--case-set", choices=tuple(CASE_SETS), default="public_30_residue")
    parser.add_argument("--paths", nargs="*", help="optional explicit instance paths")
    parser.add_argument("--max-restarts", type=int, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def _run_solve_command(
    *,
    path: str,
    time_limit: float,
    seed: int,
    max_restarts: int | None,
    dry_run: bool,
) -> dict[str, object]:
    command = [
        sys.executable,
        "main.py",
        "solve",
        path,
        "--backend",
        "cp",
        "--time-limit",
        str(time_limit),
        "--seed",
        str(seed),
        "--json",
    ]
    if max_restarts is not None:
        command.extend(["--max-restarts", str(max_restarts)])

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


def _print_row(row: dict[str, object]) -> None:
    parts = [
        f"{row['path']}:",
        str(row["status"]),
        f"mk={row['makespan']}",
        f"wall={row['runtime_seconds']:.4f}s",
        f"nodes={row['search_nodes']}",
        f"inc={row['incumbent_updates']}",
        f"gs_fail={row['guided_seed_failed']}",
        f"no_inc={row['no_incumbent_before_dfs']}",
        f"h_fail={row['heuristic_construct_failures']}",
        f"h_top={row['heuristic_construct_top_failure_reason']}",
        f"nl_fail={row['node_local_construct_failures']}",
        f"nl_top={row['node_local_construct_top_failure_reason']}",
        f"seed_top={row['seed_construct_top_failure_reason']}",
        f"prop_prune={row['propagation_pruned_nodes']}",
    ]
    print(" ".join(parts), flush=True)


def main() -> int:
    args = parse_args()
    paths = list(args.paths or CASE_SETS[args.case_set])
    if not paths:
        raise SystemExit("No residue cases selected.")

    output_dir = args.output_dir
    if output_dir is not None and not args.dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, object]] = []
    for index, path in enumerate(paths):
        payload = _run_solve_command(
            path=path,
            time_limit=args.time_limit,
            seed=args.seed + index,
            max_restarts=args.max_restarts,
            dry_run=args.dry_run,
        )
        if args.dry_run:
            continue

        metadata = payload.get("metadata", {})
        row = {
            "path": path,
            "status": payload["status"],
            "makespan": payload["makespan"],
            "runtime_seconds": float(payload["runtime_seconds"]),
            "solver_runtime_seconds": float(payload["solver_runtime_seconds"]),
            "search_nodes": int(metadata.get("search_nodes") or 0),
            "incumbent_updates": int(metadata.get("incumbent_updates") or 0),
            "guided_seed_failed": bool(metadata.get("guided_seed_failed")),
            "no_incumbent_before_dfs": bool(metadata.get("no_incumbent_before_dfs")),
            "heuristic_construct_failures": int(
                metadata.get("heuristic_construct_failures") or 0
            ),
            "heuristic_construct_top_failure_reason": str(
                metadata.get("heuristic_construct_top_failure_reason") or "none"
            ),
            "node_local_construct_failures": int(
                metadata.get("node_local_construct_failures") or 0
            ),
            "node_local_construct_top_failure_reason": str(
                metadata.get("node_local_construct_top_failure_reason") or "none"
            ),
            "seed_construct_top_failure_reason": str(
                metadata.get("seed_construct_top_failure_reason") or "none"
            ),
            "propagation_pruned_nodes": int(
                metadata.get("propagation_pruned_nodes") or 0
            ),
            "reason": metadata.get("reason"),
            "metadata": metadata,
        }
        rows.append(row)
        _print_row(row)

        if output_dir is not None:
            safe_name = path.replace("/", "__")
            (output_dir / f"{safe_name}.json").write_text(json.dumps(payload, indent=2))

    if args.dry_run:
        return 0

    summary = {
        "backend": "cp",
        "time_limit": args.time_limit,
        "seed": args.seed,
        "cases": len(rows),
        "feasible": sum(row["status"] == "feasible" for row in rows),
        "infeasible": sum(row["status"] == "infeasible" for row in rows),
        "unknown": sum(row["status"] == "unknown" for row in rows),
        "avg_runtime_seconds": (
            sum(float(row["runtime_seconds"]) for row in rows) / max(1, len(rows))
        ),
        "avg_search_nodes": (
            sum(int(row["search_nodes"]) for row in rows) / max(1, len(rows))
        ),
        "guided_seed_failed_cases": sum(bool(row["guided_seed_failed"]) for row in rows),
        "no_incumbent_before_dfs_cases": sum(
            bool(row["no_incumbent_before_dfs"]) for row in rows
        ),
        "heuristic_construct_failures": sum(
            int(row["heuristic_construct_failures"]) for row in rows
        ),
        "node_local_construct_failures": sum(
            int(row["node_local_construct_failures"]) for row in rows
        ),
        "propagation_pruned_nodes": sum(
            int(row["propagation_pruned_nodes"]) for row in rows
        ),
    }
    print(json.dumps(summary, indent=2))

    if output_dir is not None:
        (output_dir / "summary.json").write_text(
            json.dumps({"summary": summary, "results": rows}, indent=2)
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
