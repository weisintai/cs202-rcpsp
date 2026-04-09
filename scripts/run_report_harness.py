#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

import benchmark_rcpsp


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = ROOT / "report_runs" / "latest"


@dataclass(frozen=True)
class BenchmarkRun:
    name: str
    dataset: str
    solver_args: list[str]
    timeout_seconds: float
    allow_infeasible_input: bool = False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the report-facing RCPSP validation and Experiments 1-4."
    )
    parser.add_argument(
        "--stage",
        action="append",
        choices=["validation", "experiment1", "experiment2", "experiment3", "experiment4", "all"],
        help="Stage(s) to run. Defaults to all.",
    )
    parser.add_argument(
        "--solver",
        type=Path,
        help="Path to the solver binary. Defaults to ./solver.exe on Windows or ./solver otherwise.",
    )
    parser.add_argument(
        "--build-cmd",
        help="Optional one-time build command to run before the harness starts.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Directory where fresh report rerun artifacts will be written.",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Delete the output root before running.",
    )
    parser.add_argument("--limit", type=int, default=0, help="Only run the first N instances per benchmark.")
    parser.add_argument("--match", help="Only run instances whose filename contains this substring.")
    parser.add_argument(
        "--instance-list",
        type=Path,
        help="Optional text file of exact instance basenames to run.",
    )
    parser.add_argument(
        "--keep-all-artifacts",
        action="store_true",
        help="Store stdout/stderr artifacts for every instance, not just failures.",
    )
    return parser.parse_args()


def default_solver_path() -> Path:
    candidates = [ROOT / "solver.exe", ROOT / "solver"]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0] if sys.platform.startswith("win") else candidates[1]


def stage_selection(raw: list[str] | None) -> list[str]:
    if not raw or "all" in raw:
        return ["validation", "experiment1", "experiment2", "experiment3", "experiment4"]

    seen: list[str] = []
    for item in raw:
        if item not in seen:
            seen.append(item)
    return seen


def fmt_float(value: float | None, digits: int = 3) -> str:
    if value is None:
        return "-"
    return f"{value:.{digits}f}"


def fmt_match(match_count: int | None, instance_count: int | None) -> str:
    if match_count is None or instance_count is None:
        return "-"
    return f"{match_count} / {instance_count}"


def match_rate(summary: dict[str, object]) -> float | None:
    instance_count = int(summary["instance_count"])
    if instance_count == 0:
        return None
    return 100.0 * int(summary["best_known_match_count"]) / instance_count


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    header_row = "| " + " | ".join(headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([header_row, separator, *body])


def load_summary(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def benchmark_namespace(
    run: BenchmarkRun,
    solver_path: Path,
    output_dir: Path,
    *,
    limit: int,
    match: str | None,
    instance_list: Path | None,
    keep_all_artifacts: bool,
) -> argparse.Namespace:
    return argparse.Namespace(
        command="run",
        dataset=run.dataset,
        solver=str(solver_path),
        solver_args_json=json.dumps(run.solver_args),
        build_cmd=None,
        timeout=run.timeout_seconds,
        limit=limit,
        match=match,
        instance_list=instance_list,
        output_dir=output_dir,
        keep_all_artifacts=keep_all_artifacts,
        allow_infeasible_input=run.allow_infeasible_input,
    )


def execute_run(
    run: BenchmarkRun,
    solver_path: Path,
    output_dir: Path,
    *,
    limit: int,
    match: str | None,
    instance_list: Path | None,
    keep_all_artifacts: bool,
) -> dict[str, object]:
    args = benchmark_namespace(
        run,
        solver_path,
        output_dir,
        limit=limit,
        match=match,
        instance_list=instance_list,
        keep_all_artifacts=keep_all_artifacts,
    )
    benchmark_rcpsp.benchmark_solver(args)
    return load_summary(output_dir / "summary.json")


def validation_runs() -> list[BenchmarkRun]:
    solver_args = ["--time", "3", "--mode", "full"]
    return [
        BenchmarkRun("j10_full", "j10", solver_args, 5.0, allow_infeasible_input=True),
        BenchmarkRun("j20_full", "j20", solver_args, 5.0, allow_infeasible_input=True),
    ]


def experiment1_runs() -> list[BenchmarkRun]:
    configs = [
        ("baseline", ["--time", "3", "--mode", "baseline"]),
        ("priority", ["--time", "3", "--mode", "priority"]),
        ("ga", ["--time", "3", "--mode", "ga"]),
        ("full", ["--time", "3", "--mode", "full"]),
    ]
    runs: list[BenchmarkRun] = []
    for name, solver_args in configs:
        for dataset in ("j30", "j60"):
            runs.append(BenchmarkRun(f"{name}_{dataset}", dataset, solver_args, 5.0))
    return runs


def experiment2_runs() -> list[BenchmarkRun]:
    return [
        BenchmarkRun(dataset, dataset, ["--time", "3", "--mode", "full"], 5.0)
        for dataset in ("j30", "j60", "j90", "j120")
    ]


def experiment3_runs() -> list[BenchmarkRun]:
    runs: list[BenchmarkRun] = []
    for budget in (1, 3, 10, 28):
        for dataset in ("j30", "j60"):
            runs.append(
                BenchmarkRun(
                    f"{budget}s_{dataset}",
                    dataset,
                    ["--time", str(budget), "--mode", "full"],
                    float(budget + 2),
                )
            )
    return runs


def experiment4_runs() -> list[BenchmarkRun]:
    runs: list[BenchmarkRun] = []
    for rule in ("random", "lft", "mts", "grd", "spt"):
        for dataset in ("j30", "j60"):
            runs.append(BenchmarkRun(f"{rule}_{dataset}", dataset, ["--rule", rule], 5.0))
    return runs


def summarise_validation(stage_dir: Path) -> dict[str, object]:
    payload: dict[str, object] = {}
    rows: list[list[str]] = []
    for dataset in ("j10", "j20"):
        summary = load_summary(stage_dir / f"{dataset}_full" / "summary.json")
        payload[dataset] = summary
        rows.append(
            [
                dataset.upper(),
                str(summary["instance_count"]),
                str(summary["ok_count"]),
                str(summary["infeasible_count"]),
                str(summary["timeout_count"]),
                str(summary["invalid_count"]),
                fmt_float(summary["mean_wall_time_seconds"]),
            ]
        )

    md = "\n".join(
        [
            "# Validation Summary",
            "",
            markdown_table(
                ["Dataset", "Instances", "OK", "Infeasible", "Timeouts", "Other invalid", "Mean wall time (s)"],
                rows,
            ),
            "",
            "The validation stage uses the current full solver on the local J10 and J20 sets.",
            "Known infeasible local inputs are counted separately and do not fail the harness.",
        ]
    )
    write_json(stage_dir / "comparison.json", payload)
    write_text(stage_dir / "comparison.md", md + "\n")
    return payload


def summarise_experiment1(stage_dir: Path) -> dict[str, object]:
    payload: dict[str, object] = {}
    rows: list[list[str]] = []
    for config in ("baseline", "priority", "ga", "full"):
        j30 = load_summary(stage_dir / f"{config}_j30" / "summary.json")
        j60 = load_summary(stage_dir / f"{config}_j60" / "summary.json")
        payload[config] = {"j30": j30, "j60": j60}
        rows.append(
            [
                config,
                fmt_float(match_rate(j30), 2),
                fmt_float(j30["mean_gap_to_best_known_pct"]),
                fmt_float(match_rate(j60), 2),
                fmt_float(j60["mean_gap_to_best_known_pct"]),
            ]
        )

    md = "\n".join(
        [
            "# Experiment 1 Summary",
            "",
            markdown_table(
                ["Configuration", "J30 match rate (%)", "J30 mean gap (%)", "J60 match rate (%)", "J60 mean gap (%)"],
                rows,
            ),
        ]
    )
    write_json(stage_dir / "comparison.json", payload)
    write_text(stage_dir / "comparison.md", md + "\n")
    return payload


def summarise_experiment2(stage_dir: Path) -> dict[str, object]:
    payload: dict[str, object] = {}
    rows: list[list[str]] = []
    for dataset in ("j30", "j60", "j90", "j120"):
        summary = load_summary(stage_dir / dataset / "summary.json")
        payload[dataset] = summary
        rows.append(
            [
                dataset.upper(),
                fmt_match(int(summary["best_known_match_count"]), int(summary["instance_count"])),
                fmt_float(match_rate(summary), 2),
                fmt_float(summary["mean_gap_to_best_known_pct"]),
                fmt_float(summary["mean_quality_vs_best_known_pct"]),
                fmt_float(summary["max_gap_to_best_known_pct"]),
                fmt_float(summary["mean_wall_time_seconds"]),
            ]
        )

    md = "\n".join(
        [
            "# Experiment 2 Summary",
            "",
            markdown_table(
                [
                    "Dataset",
                    "Best-known matches",
                    "Match rate (%)",
                    "Mean gap (%)",
                    "Mean quality (%)",
                    "Max gap (%)",
                    "Mean wall time (s)",
                ],
                rows,
            ),
        ]
    )
    write_json(stage_dir / "comparison.json", payload)
    write_text(stage_dir / "comparison.md", md + "\n")
    return payload


def summarise_experiment3(stage_dir: Path) -> dict[str, object]:
    payload: dict[str, object] = {}
    rows: list[list[str]] = []
    for budget in ("1s", "3s", "10s", "28s"):
        j30 = load_summary(stage_dir / f"{budget}_j30" / "summary.json")
        j60 = load_summary(stage_dir / f"{budget}_j60" / "summary.json")
        payload[budget] = {"j30": j30, "j60": j60}
        rows.append(
            [
                budget,
                fmt_match(int(j30["best_known_match_count"]), int(j30["instance_count"])),
                fmt_float(j30["mean_gap_to_best_known_pct"]),
                fmt_float(j30["mean_quality_vs_best_known_pct"]),
                fmt_match(int(j60["best_known_match_count"]), int(j60["instance_count"])),
                fmt_float(j60["mean_gap_to_best_known_pct"]),
                fmt_float(j60["mean_quality_vs_best_known_pct"]),
            ]
        )

    md = "\n".join(
        [
            "# Experiment 3 Summary",
            "",
            markdown_table(
                [
                    "Time budget",
                    "J30 best-known matches",
                    "J30 mean gap (%)",
                    "J30 mean quality (%)",
                    "J60 best-known matches",
                    "J60 mean gap (%)",
                    "J60 mean quality (%)",
                ],
                rows,
            ),
        ]
    )
    write_json(stage_dir / "comparison.json", payload)
    write_text(stage_dir / "comparison.md", md + "\n")
    return payload


def summarise_experiment4(stage_dir: Path) -> dict[str, object]:
    payload: dict[str, object] = {}
    rows: list[list[str]] = []
    for rule in ("random", "lft", "mts", "grd", "spt"):
        j30 = load_summary(stage_dir / f"{rule}_j30" / "summary.json")
        j60 = load_summary(stage_dir / f"{rule}_j60" / "summary.json")
        payload[rule] = {"j30": j30, "j60": j60}
        rows.append(
            [
                rule,
                fmt_match(int(j30["best_known_match_count"]), int(j30["instance_count"])),
                fmt_float(j30["mean_gap_to_best_known_pct"]),
                fmt_float(j30["mean_quality_vs_best_known_pct"]),
                fmt_match(int(j60["best_known_match_count"]), int(j60["instance_count"])),
                fmt_float(j60["mean_gap_to_best_known_pct"]),
                fmt_float(j60["mean_quality_vs_best_known_pct"]),
            ]
        )

    md = "\n".join(
        [
            "# Experiment 4 Summary",
            "",
            markdown_table(
                [
                    "Rule",
                    "J30 best-known matches",
                    "J30 mean gap (%)",
                    "J30 mean quality (%)",
                    "J60 best-known matches",
                    "J60 mean gap (%)",
                    "J60 mean quality (%)",
                ],
                rows,
            ),
        ]
    )
    write_json(stage_dir / "comparison.json", payload)
    write_text(stage_dir / "comparison.md", md + "\n")
    return payload


def run_stage(
    stage_name: str,
    runs: list[BenchmarkRun],
    output_root: Path,
    solver_path: Path,
    *,
    limit: int,
    match: str | None,
    instance_list: Path | None,
    keep_all_artifacts: bool,
) -> dict[str, object]:
    stage_dir = output_root / stage_name
    if stage_dir.exists():
        shutil.rmtree(stage_dir)
    stage_dir.mkdir(parents=True, exist_ok=True)

    print()
    print(f"=== {stage_name} ===")
    for run in runs:
        print(f"run {run.name}: dataset={run.dataset} args={run.solver_args}")
        execute_run(
            run,
            solver_path,
            stage_dir / run.name,
            limit=limit,
            match=match,
            instance_list=instance_list,
            keep_all_artifacts=keep_all_artifacts,
        )

    if stage_name == "validation":
        return summarise_validation(stage_dir)
    if stage_name == "experiment1":
        return summarise_experiment1(stage_dir)
    if stage_name == "experiment2":
        return summarise_experiment2(stage_dir)
    if stage_name == "experiment3":
        return summarise_experiment3(stage_dir)
    if stage_name == "experiment4":
        return summarise_experiment4(stage_dir)
    raise ValueError(f"unsupported stage: {stage_name}")


def write_manifest(output_root: Path, stages: list[str], solver_path: Path) -> None:
    manifest = {
        "solver": str(solver_path),
        "stages": stages,
        "output_root": str(output_root),
        "stage_summaries": {
            stage: {
                "comparison_json": str((output_root / stage / "comparison.json").relative_to(ROOT)),
                "comparison_md": str((output_root / stage / "comparison.md").relative_to(ROOT)),
            }
            for stage in stages
        },
    }
    write_json(output_root / "manifest.json", manifest)

    rows = [
        [
            stage,
            str((output_root / stage / "comparison.json").relative_to(ROOT)),
            str((output_root / stage / "comparison.md").relative_to(ROOT)),
        ]
        for stage in stages
    ]
    md = "\n".join(
        [
            "# Report Harness Manifest",
            "",
            f"Solver: `{solver_path}`",
            "",
            markdown_table(["Stage", "comparison.json", "comparison.md"], rows),
        ]
    )
    write_text(output_root / "manifest.md", md + "\n")


def main() -> None:
    args = parse_args()
    stages = stage_selection(args.stage)

    solver_path = args.solver if args.solver else default_solver_path()
    if not solver_path.is_absolute():
        solver_path = (ROOT / solver_path).resolve()

    output_root = args.output_root
    if not output_root.is_absolute():
        output_root = ROOT / output_root

    if args.clean and output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    if args.build_cmd:
        benchmark_rcpsp.run_build_command(args.build_cmd)

    if not solver_path.exists():
        raise SystemExit(f"solver not found: {solver_path}")

    if args.instance_list and not args.instance_list.is_absolute():
        args.instance_list = ROOT / args.instance_list

    stage_runs = {
        "validation": validation_runs(),
        "experiment1": experiment1_runs(),
        "experiment2": experiment2_runs(),
        "experiment3": experiment3_runs(),
        "experiment4": experiment4_runs(),
    }

    for stage_name in stages:
        run_stage(
            stage_name,
            stage_runs[stage_name],
            output_root,
            solver_path,
            limit=args.limit,
            match=args.match,
            instance_list=args.instance_list,
            keep_all_artifacts=args.keep_all_artifacts,
        )

    write_manifest(output_root, stages, solver_path)
    print()
    print(f"Report harness complete. Results written to {output_root}")


if __name__ == "__main__":
    main()
