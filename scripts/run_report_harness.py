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
MODE_CHOICES = ("baseline", "priority", "ga", "full")
EXPERIMENT1_CONFIGS = ("baseline", "priority", "ga", "full")
EXPERIMENT4_RULES = ("random", "lft", "mts", "grd", "spt")
VALIDATION_DATASETS = ("j10", "j20")
EXPERIMENT1_DATASETS = ("j30", "j60")
EXPERIMENT2_DATASETS = ("j30", "j60", "j90", "j120")
EXPERIMENT3_DATASETS = ("j30", "j60")
EXPERIMENT4_DATASETS = ("j30", "j60")


@dataclass(frozen=True)
class BenchmarkRun:
    name: str
    dataset: str
    solver_args: list[str]
    timeout_seconds: float
    series: str
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

    parser.add_argument("--validation-datasets", help="Comma-separated subset of: j10,j20")
    parser.add_argument("--validation-time", type=float, help="Override the validation time budget in seconds.")
    parser.add_argument(
        "--validation-mode",
        choices=MODE_CHOICES,
        help="Override the validation solver mode. Default: full.",
    )

    parser.add_argument("--experiment1-datasets", help="Comma-separated subset of: j30,j60")
    parser.add_argument(
        "--experiment1-configs",
        help="Comma-separated subset of: baseline,priority,ga,full",
    )
    parser.add_argument("--experiment1-time", type=float, help="Override the Experiment 1 time budget in seconds.")

    parser.add_argument("--experiment2-datasets", help="Comma-separated subset of: j30,j60,j90,j120")
    parser.add_argument("--experiment2-time", type=float, help="Override the Experiment 2 time budget in seconds.")
    parser.add_argument(
        "--experiment2-mode",
        choices=MODE_CHOICES,
        help="Override the Experiment 2 solver mode. Default: full.",
    )

    parser.add_argument("--experiment3-datasets", help="Comma-separated subset of: j30,j60")
    parser.add_argument(
        "--experiment3-time-budgets",
        help="Comma-separated list of time budgets in seconds. Default: 1,3,10,28",
    )
    parser.add_argument(
        "--experiment3-mode",
        choices=MODE_CHOICES,
        help="Override the Experiment 3 solver mode. Default: full.",
    )

    parser.add_argument("--experiment4-datasets", help="Comma-separated subset of: j30,j60")
    parser.add_argument(
        "--experiment4-rules",
        help="Comma-separated subset of: random,lft,mts,grd,spt",
    )
    parser.add_argument("--experiment4-time", type=float, help="Override the Experiment 4 time budget in seconds.")

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


def unique_preserve(values: list[str]) -> list[str]:
    seen: list[str] = []
    for value in values:
        if value not in seen:
            seen.append(value)
    return seen


def parse_csv_choices(raw: str | None, allowed: tuple[str, ...], option_name: str) -> list[str] | None:
    if raw is None:
        return None
    values = [item.strip().lower() for item in raw.split(",") if item.strip()]
    if not values:
        raise SystemExit(f"{option_name} requires at least one value")
    invalid = [value for value in values if value not in allowed]
    if invalid:
        raise SystemExit(f"{option_name} contains unsupported values: {', '.join(invalid)}")
    return unique_preserve(values)


def parse_time_budgets(raw: str | None, option_name: str) -> list[float] | None:
    if raw is None:
        return None
    budgets: list[float] = []
    seen: set[str] = set()
    for piece in raw.split(","):
        token = piece.strip()
        if not token:
            continue
        try:
            value = float(token)
        except ValueError as exc:
            raise SystemExit(f"{option_name} contains a non-numeric value: {token}") from exc
        if value <= 0:
            raise SystemExit(f"{option_name} only accepts positive values")
        normalized = f"{value:g}"
        if normalized not in seen:
            seen.add(normalized)
            budgets.append(value)
    if not budgets:
        raise SystemExit(f"{option_name} requires at least one value")
    return budgets


def format_budget(value: float) -> str:
    return f"{value:g}"


def budget_label(value: float) -> str:
    return f"{value:g}s"


def timeout_from_budget(time_budget: float, minimum: float = 5.0) -> float:
    return max(minimum, time_budget + 2.0)


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


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def solver_args_text(solver_args: list[str]) -> str:
    return " ".join(solver_args)


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


def validation_runs(args: argparse.Namespace) -> list[BenchmarkRun]:
    datasets = parse_csv_choices(args.validation_datasets, VALIDATION_DATASETS, "--validation-datasets") or list(
        VALIDATION_DATASETS
    )
    time_budget = args.validation_time if args.validation_time is not None else 3.0
    mode = args.validation_mode or "full"
    solver_args = ["--time", format_budget(time_budget), "--mode", mode]
    return [
        BenchmarkRun(
            name=f"{dataset}_{mode}",
            dataset=dataset,
            solver_args=solver_args,
            timeout_seconds=timeout_from_budget(time_budget),
            series=dataset,
            allow_infeasible_input=True,
        )
        for dataset in datasets
    ]


def experiment1_runs(args: argparse.Namespace) -> list[BenchmarkRun]:
    datasets = parse_csv_choices(args.experiment1_datasets, EXPERIMENT1_DATASETS, "--experiment1-datasets") or list(
        EXPERIMENT1_DATASETS
    )
    configs = parse_csv_choices(args.experiment1_configs, EXPERIMENT1_CONFIGS, "--experiment1-configs") or list(
        EXPERIMENT1_CONFIGS
    )
    time_budget = args.experiment1_time if args.experiment1_time is not None else 3.0
    timeout_seconds = timeout_from_budget(time_budget)
    runs: list[BenchmarkRun] = []
    for config in configs:
        solver_args = ["--time", format_budget(time_budget), "--mode", config]
        for dataset in datasets:
            runs.append(
                BenchmarkRun(
                    name=f"{config}_{dataset}",
                    dataset=dataset,
                    solver_args=solver_args,
                    timeout_seconds=timeout_seconds,
                    series=config,
                )
            )
    return runs


def experiment2_runs(args: argparse.Namespace) -> list[BenchmarkRun]:
    datasets = parse_csv_choices(args.experiment2_datasets, EXPERIMENT2_DATASETS, "--experiment2-datasets") or list(
        EXPERIMENT2_DATASETS
    )
    time_budget = args.experiment2_time if args.experiment2_time is not None else 3.0
    mode = args.experiment2_mode or "full"
    return [
        BenchmarkRun(
            name=dataset,
            dataset=dataset,
            solver_args=["--time", format_budget(time_budget), "--mode", mode],
            timeout_seconds=timeout_from_budget(time_budget),
            series=dataset,
        )
        for dataset in datasets
    ]


def experiment3_runs(args: argparse.Namespace) -> list[BenchmarkRun]:
    datasets = parse_csv_choices(args.experiment3_datasets, EXPERIMENT3_DATASETS, "--experiment3-datasets") or list(
        EXPERIMENT3_DATASETS
    )
    budgets = parse_time_budgets(args.experiment3_time_budgets, "--experiment3-time-budgets") or [1.0, 3.0, 10.0, 28.0]
    mode = args.experiment3_mode or "full"
    runs: list[BenchmarkRun] = []
    for budget in budgets:
        label = budget_label(budget)
        solver_args = ["--time", format_budget(budget), "--mode", mode]
        for dataset in datasets:
            runs.append(
                BenchmarkRun(
                    name=f"{label}_{dataset}",
                    dataset=dataset,
                    solver_args=solver_args,
                    timeout_seconds=timeout_from_budget(budget),
                    series=label,
                )
            )
    return runs


def experiment4_runs(args: argparse.Namespace) -> list[BenchmarkRun]:
    datasets = parse_csv_choices(args.experiment4_datasets, EXPERIMENT4_DATASETS, "--experiment4-datasets") or list(
        EXPERIMENT4_DATASETS
    )
    rules = parse_csv_choices(args.experiment4_rules, EXPERIMENT4_RULES, "--experiment4-rules") or list(
        EXPERIMENT4_RULES
    )
    time_budget = args.experiment4_time if args.experiment4_time is not None else 3.0
    timeout_seconds = timeout_from_budget(time_budget)
    runs: list[BenchmarkRun] = []
    for rule in rules:
        solver_args = ["--time", format_budget(time_budget), "--rule", rule]
        for dataset in datasets:
            runs.append(
                BenchmarkRun(
                    name=f"{rule}_{dataset}",
                    dataset=dataset,
                    solver_args=solver_args,
                    timeout_seconds=timeout_seconds,
                    series=rule,
                )
            )
    return runs


def collect_stage_entries(stage_dir: Path, runs: list[BenchmarkRun]) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for run in runs:
        entries.append(
            {
                "name": run.name,
                "series": run.series,
                "dataset": run.dataset,
                "solver_args": run.solver_args,
                "timeout_seconds": run.timeout_seconds,
                "allow_infeasible_input": run.allow_infeasible_input,
                "summary": load_summary(stage_dir / run.name / "summary.json"),
            }
        )
    return entries


def configured_runs_markdown(entries: list[dict[str, object]]) -> str:
    rows = [
        [
            str(entry["name"]),
            str(entry["series"]),
            str(entry["dataset"]).upper(),
            solver_args_text(list(entry["solver_args"])),
            fmt_float(float(entry["timeout_seconds"]), 1),
        ]
        for entry in entries
    ]
    return markdown_table(["Run", "Series", "Dataset", "Solver args", "Timeout (s)"], rows)


def grouped_stage_markdown(
    *,
    title: str,
    row_title: str,
    dataset_order: list[str],
    series_order: list[str],
    summary_lookup: dict[tuple[str, str], dict[str, object]],
    metric_specs: list[tuple[str, callable]],
    entries: list[dict[str, object]],
) -> str:
    headers = [row_title]
    for dataset in dataset_order:
        for metric_name, _ in metric_specs:
            headers.append(f"{dataset.upper()} {metric_name}")

    rows: list[list[str]] = []
    for series in series_order:
        row = [series]
        for dataset in dataset_order:
            summary = summary_lookup.get((series, dataset))
            for _, formatter in metric_specs:
                row.append(formatter(summary) if summary is not None else "-")
        rows.append(row)

    return "\n".join(
        [
            f"# {title}",
            "",
            "## Configured runs",
            "",
            configured_runs_markdown(entries),
            "",
            "## Aggregated metrics",
            "",
            markdown_table(headers, rows),
        ]
    )


def summarise_validation(stage_dir: Path, runs: list[BenchmarkRun]) -> dict[str, object]:
    entries = collect_stage_entries(stage_dir, runs)
    rows = [
        [
            str(entry["dataset"]).upper(),
            str(entry["name"]),
            solver_args_text(list(entry["solver_args"])),
            fmt_float(float(entry["timeout_seconds"]), 1),
            str(entry["summary"]["instance_count"]),
            str(entry["summary"]["ok_count"]),
            str(entry["summary"]["infeasible_count"]),
            str(entry["summary"]["timeout_count"]),
            str(entry["summary"]["invalid_count"]),
            fmt_float(entry["summary"]["mean_wall_time_seconds"]),
        ]
        for entry in entries
    ]

    md = "\n".join(
        [
            "# Validation Summary",
            "",
            markdown_table(
                [
                    "Dataset",
                    "Run",
                    "Solver args",
                    "Timeout (s)",
                    "Instances",
                    "OK",
                    "Infeasible",
                    "Timeouts",
                    "Other invalid",
                    "Mean wall time (s)",
                ],
                rows,
            ),
            "",
            "Known infeasible local inputs are counted separately and do not fail the harness.",
        ]
    )
    payload = {"runs": entries}
    write_json(stage_dir / "comparison.json", payload)
    write_text(stage_dir / "comparison.md", md + "\n")
    return payload


def summarise_experiment1(stage_dir: Path, runs: list[BenchmarkRun]) -> dict[str, object]:
    entries = collect_stage_entries(stage_dir, runs)
    dataset_order = unique_preserve([run.dataset for run in runs])
    series_order = unique_preserve([run.series for run in runs])
    summary_lookup = {(str(entry["series"]), str(entry["dataset"])): entry["summary"] for entry in entries}
    metric_specs = [
        ("match rate (%)", lambda summary: fmt_float(match_rate(summary), 2)),
        ("mean gap (%)", lambda summary: fmt_float(summary["mean_gap_to_best_known_pct"])),
    ]
    payload = {"datasets": dataset_order, "series": series_order, "runs": entries}
    md = grouped_stage_markdown(
        title="Experiment 1 Summary",
        row_title="Configuration",
        dataset_order=dataset_order,
        series_order=series_order,
        summary_lookup=summary_lookup,
        metric_specs=metric_specs,
        entries=entries,
    )
    write_json(stage_dir / "comparison.json", payload)
    write_text(stage_dir / "comparison.md", md + "\n")
    return payload


def summarise_experiment2(stage_dir: Path, runs: list[BenchmarkRun]) -> dict[str, object]:
    entries = collect_stage_entries(stage_dir, runs)
    rows = [
        [
            str(entry["dataset"]).upper(),
            str(entry["name"]),
            solver_args_text(list(entry["solver_args"])),
            fmt_float(float(entry["timeout_seconds"]), 1),
            fmt_match(
                int(entry["summary"]["best_known_match_count"]),
                int(entry["summary"]["instance_count"]),
            ),
            fmt_float(match_rate(entry["summary"]), 2),
            fmt_float(entry["summary"]["mean_gap_to_best_known_pct"]),
            fmt_float(entry["summary"]["mean_quality_vs_best_known_pct"]),
            fmt_float(entry["summary"]["max_gap_to_best_known_pct"]),
            fmt_float(entry["summary"]["mean_wall_time_seconds"]),
        ]
        for entry in entries
    ]

    md = "\n".join(
        [
            "# Experiment 2 Summary",
            "",
            markdown_table(
                [
                    "Dataset",
                    "Run",
                    "Solver args",
                    "Timeout (s)",
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
    payload = {"runs": entries}
    write_json(stage_dir / "comparison.json", payload)
    write_text(stage_dir / "comparison.md", md + "\n")
    return payload


def summarise_experiment3(stage_dir: Path, runs: list[BenchmarkRun]) -> dict[str, object]:
    entries = collect_stage_entries(stage_dir, runs)
    dataset_order = unique_preserve([run.dataset for run in runs])
    series_order = unique_preserve([run.series for run in runs])
    summary_lookup = {(str(entry["series"]), str(entry["dataset"])): entry["summary"] for entry in entries}
    metric_specs = [
        (
            "best-known matches",
            lambda summary: fmt_match(
                int(summary["best_known_match_count"]),
                int(summary["instance_count"]),
            ),
        ),
        ("mean gap (%)", lambda summary: fmt_float(summary["mean_gap_to_best_known_pct"])),
        ("mean quality (%)", lambda summary: fmt_float(summary["mean_quality_vs_best_known_pct"])),
    ]
    payload = {"datasets": dataset_order, "series": series_order, "runs": entries}
    md = grouped_stage_markdown(
        title="Experiment 3 Summary",
        row_title="Time budget",
        dataset_order=dataset_order,
        series_order=series_order,
        summary_lookup=summary_lookup,
        metric_specs=metric_specs,
        entries=entries,
    )
    write_json(stage_dir / "comparison.json", payload)
    write_text(stage_dir / "comparison.md", md + "\n")
    return payload


def summarise_experiment4(stage_dir: Path, runs: list[BenchmarkRun]) -> dict[str, object]:
    entries = collect_stage_entries(stage_dir, runs)
    dataset_order = unique_preserve([run.dataset for run in runs])
    series_order = unique_preserve([run.series for run in runs])
    summary_lookup = {(str(entry["series"]), str(entry["dataset"])): entry["summary"] for entry in entries}
    metric_specs = [
        (
            "best-known matches",
            lambda summary: fmt_match(
                int(summary["best_known_match_count"]),
                int(summary["instance_count"]),
            ),
        ),
        ("mean gap (%)", lambda summary: fmt_float(summary["mean_gap_to_best_known_pct"])),
        ("mean quality (%)", lambda summary: fmt_float(summary["mean_quality_vs_best_known_pct"])),
    ]
    payload = {"datasets": dataset_order, "series": series_order, "runs": entries}
    md = grouped_stage_markdown(
        title="Experiment 4 Summary",
        row_title="Rule",
        dataset_order=dataset_order,
        series_order=series_order,
        summary_lookup=summary_lookup,
        metric_specs=metric_specs,
        entries=entries,
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
    if not runs:
        raise SystemExit(f"no runs configured for stage {stage_name}")

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
        return summarise_validation(stage_dir, runs)
    if stage_name == "experiment1":
        return summarise_experiment1(stage_dir, runs)
    if stage_name == "experiment2":
        return summarise_experiment2(stage_dir, runs)
    if stage_name == "experiment3":
        return summarise_experiment3(stage_dir, runs)
    if stage_name == "experiment4":
        return summarise_experiment4(stage_dir, runs)
    raise ValueError(f"unsupported stage: {stage_name}")


def serialise_runs(runs: list[BenchmarkRun]) -> list[dict[str, object]]:
    return [
        {
            "name": run.name,
            "series": run.series,
            "dataset": run.dataset,
            "solver_args": run.solver_args,
            "timeout_seconds": run.timeout_seconds,
            "allow_infeasible_input": run.allow_infeasible_input,
        }
        for run in runs
    ]


def write_manifest(output_root: Path, stages: list[str], solver_path: Path, stage_runs: dict[str, list[BenchmarkRun]]) -> None:
    manifest = {
        "solver": str(solver_path),
        "stages": stages,
        "output_root": str(output_root),
        "stage_summaries": {
            stage: {
                "comparison_json": display_path(output_root / stage / "comparison.json"),
                "comparison_md": display_path(output_root / stage / "comparison.md"),
            }
            for stage in stages
        },
        "stage_runs": {stage: serialise_runs(stage_runs[stage]) for stage in stages},
    }
    write_json(output_root / "manifest.json", manifest)

    rows = [
        [
            stage,
            str(len(stage_runs[stage])),
            display_path(output_root / stage / "comparison.json"),
            display_path(output_root / stage / "comparison.md"),
        ]
        for stage in stages
    ]
    md = "\n".join(
        [
            "# Report Harness Manifest",
            "",
            f"Solver: `{solver_path}`",
            "",
            markdown_table(["Stage", "Run count", "comparison.json", "comparison.md"], rows),
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

    stage_builders = {
        "validation": validation_runs,
        "experiment1": experiment1_runs,
        "experiment2": experiment2_runs,
        "experiment3": experiment3_runs,
        "experiment4": experiment4_runs,
    }
    stage_runs = {stage: stage_builders[stage](args) for stage in stages}

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

    write_manifest(output_root, stages, solver_path, stage_runs)
    print()
    print(f"Report harness complete. Results written to {output_root}")


if __name__ == "__main__":
    main()
