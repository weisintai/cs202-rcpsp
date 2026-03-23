from __future__ import annotations

import json
import platform
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = ROOT / "tmp" / "guardrails"


@dataclass(frozen=True)
class GuardrailCase:
    dataset: str
    time_limit: float
    benchmark_path: str | None = None


EXTERNAL_DATA_ROOT = ROOT / "references" / "kobe-scheduling" / "data" / "rcpsp-max"


PRESETS: dict[str, tuple[GuardrailCase, ...]] = {
    "quick": (
        GuardrailCase("sm_j10", 0.1),
        GuardrailCase("sm_j20", 0.1),
        GuardrailCase("sm_j30", 0.1),
        GuardrailCase("testset_ubo50", 0.1),
    ),
    "research_quick": (
        GuardrailCase("sm_j10", 0.1),
        GuardrailCase("sm_j20", 0.1),
        GuardrailCase("sm_j30", 0.1),
        GuardrailCase("testset_ubo20", 0.1),
        GuardrailCase("testset_ubo50", 0.1),
    ),
    "medium": (
        GuardrailCase("sm_j10", 1.0),
        GuardrailCase("sm_j20", 1.0),
    ),
    "full": (
        GuardrailCase("sm_j10", 0.1),
        GuardrailCase("sm_j20", 0.1),
        GuardrailCase("sm_j30", 0.1),
        GuardrailCase("testset_ubo50", 0.1),
        GuardrailCase("sm_j10", 1.0),
        GuardrailCase("sm_j20", 1.0),
    ),
    "research": (
        GuardrailCase("sm_j10", 0.1),
        GuardrailCase("sm_j20", 0.1),
        GuardrailCase("sm_j30", 0.1),
        GuardrailCase("testset_ubo20", 0.1),
        GuardrailCase("testset_ubo50", 0.1),
        GuardrailCase("sm_j10", 1.0),
        GuardrailCase("sm_j20", 1.0),
    ),
    "submission_quick": (
        GuardrailCase("sm_j10", 1.0),
        GuardrailCase("sm_j20", 1.0),
        GuardrailCase("sm_j30", 0.1),
        GuardrailCase("testset_ubo20", 0.1),
        GuardrailCase("testset_ubo50", 0.1),
    ),
    "broad_generalization": (
        GuardrailCase("testset_ubo10", 0.1, benchmark_path=str(EXTERNAL_DATA_ROOT / "testset_ubo10")),
        GuardrailCase("testset_ubo100", 0.1, benchmark_path=str(EXTERNAL_DATA_ROOT / "testset_ubo100")),
        GuardrailCase("testset_ubo200", 0.1, benchmark_path=str(EXTERNAL_DATA_ROOT / "testset_ubo200")),
    ),
    "cp_acceptance": (
        GuardrailCase("sm_j10", 30),
        GuardrailCase("sm_j20", 30),
        GuardrailCase("sm_j30", 30),
        GuardrailCase("testset_ubo20", 30),
        GuardrailCase("testset_ubo50", 30),
    ),
    "submission": (
        GuardrailCase("sm_j10", 30),
        GuardrailCase("sm_j20", 30),
        GuardrailCase("sm_j30", 30),
        GuardrailCase("testset_ubo20", 30),
        GuardrailCase("testset_ubo50", 30),
        GuardrailCase("testset_ubo10", 0.1, benchmark_path=str(EXTERNAL_DATA_ROOT / "testset_ubo10")),
        GuardrailCase("testset_ubo100", 0.1, benchmark_path=str(EXTERNAL_DATA_ROOT / "testset_ubo100")),
        GuardrailCase("testset_ubo200", 0.1, benchmark_path=str(EXTERNAL_DATA_ROOT / "testset_ubo200")),
    ),
}


def format_limit(value: float) -> str:
    return str(value).replace(".", "p")


def _optional_command_output(command: list[str]) -> str | None:
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    output = completed.stdout.strip()
    return output or None


def build_run_metadata() -> dict[str, object]:
    return {
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "root": str(ROOT),
        "python_executable": sys.executable,
        "python_version": sys.version.split()[0],
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "processor": platform.processor(),
        },
        "git_commit": _optional_command_output(["git", "rev-parse", "HEAD"]),
        "git_branch": _optional_command_output(["git", "rev-parse", "--abbrev-ref", "HEAD"]),
    }


def run_json_command(command: list[str], *, dry_run: bool) -> dict:
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


def filtered_cases(*, preset: str, datasets: list[str] | None) -> list[GuardrailCase]:
    cases = list(PRESETS[preset])
    if not datasets:
        return cases
    allowed = set(datasets)
    return [case for case in cases if case.dataset in allowed]


def build_output_dir(*, backend: str, preset: str, output_dir: Path | None) -> Path:
    if output_dir is not None:
        return output_dir
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return DEFAULT_OUTPUT_ROOT / f"{backend}-{preset}-{timestamp}"


def run_guardrail_suite(
    *,
    backend: str,
    preset: str,
    datasets: list[str] | None = None,
    seed: int = 0,
    max_restarts: int | None = None,
    heuristic_args: dict[str, float] | None = None,
    output_dir: Path | None = None,
    dry_run: bool = False,
) -> dict:
    cases = filtered_cases(preset=preset, datasets=datasets)
    if not cases:
        raise SystemExit("No guardrail cases selected.")

    resolved_output_dir = build_output_dir(backend=backend, preset=preset, output_dir=output_dir)
    if not dry_run:
        resolved_output_dir.mkdir(parents=True, exist_ok=True)

    aggregate: list[dict] = []
    for case in cases:
        label = f"{case.dataset}@{case.time_limit:.1f}s"
        bench_output = resolved_output_dir / f"{case.dataset}_{format_limit(case.time_limit)}_{backend}_benchmark.json"
        compare_output = resolved_output_dir / f"{case.dataset}_{format_limit(case.time_limit)}_{backend}_compare.json"

        benchmark_command = [
            sys.executable,
            "main.py",
            "benchmark",
            case.benchmark_path or case.dataset,
            "--time-limit",
            str(case.time_limit),
            "--backend",
            backend,
            "--seed",
            str(seed),
            "--output",
            str(bench_output),
            "--no-progress",
        ]
        if max_restarts is not None:
            benchmark_command.extend(["--max-restarts", str(max_restarts)])
        if heuristic_args:
            for key, value in heuristic_args.items():
                benchmark_command.extend([f"--{key.replace('_', '-')}", str(value)])

        benchmark_summary = run_json_command(benchmark_command, dry_run=dry_run)

        compare_command = [
            sys.executable,
            "main.py",
            "compare",
            str(bench_output),
            "--dataset",
            case.dataset,
            "--output",
            str(compare_output),
            "--no-progress",
        ]
        compare_payload = run_json_command(compare_command, dry_run=dry_run)
        compare_summary = compare_payload.get("summary", {}) if compare_payload else {}

        aggregate.append(
            {
                "label": label,
                "dataset": case.dataset,
                "time_limit": case.time_limit,
                "benchmark_summary": benchmark_summary,
                "compare_summary": compare_summary,
                "benchmark_output": str(bench_output),
                "compare_output": str(compare_output),
                "benchmark_command": benchmark_command,
                "compare_command": compare_command,
            }
        )

        if dry_run:
            continue

        print(
            (
                f"{label}: "
                f"F={benchmark_summary['feasible']} "
                f"I={benchmark_summary['infeasible']} "
                f"U={benchmark_summary['unknown']} "
                f"exact={compare_summary.get('matched_exact', 0)}/{compare_summary.get('exact_cases', 0)} "
                f"rate={compare_summary.get('exact_match_rate', 0.0):.3f}"
            ),
            flush=True,
        )

    summary = {
        "backend": backend,
        "preset": preset,
        "seed": seed,
        "max_restarts": max_restarts,
        "heuristic_args": dict(heuristic_args or {}),
        "metadata": build_run_metadata(),
        "runs": aggregate,
    }
    summary_path: Path | None = None
    if not dry_run:
        summary_path = resolved_output_dir / "summary.json"
        summary_path.write_text(json.dumps(summary, indent=2))

    return {
        "backend": backend,
        "preset": preset,
        "seed": seed,
        "max_restarts": max_restarts,
        "heuristic_args": dict(heuristic_args or {}),
        "datasets": list(datasets or []),
        "output_dir": str(resolved_output_dir),
        "summary_path": str(summary_path) if summary_path is not None else None,
        "summary": summary,
    }
