#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import statistics
import subprocess
import time
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
DATASETS_ROOT = ROOT / "datasets" / "psplib"
RESULTS_ROOT = ROOT / "benchmark_results"


@dataclass(frozen=True)
class DatasetSpec:
    name: str
    file_glob: str
    format: str
    instances_dir: Path
    archive_url: str | None
    archive_name: str | None
    optimal_url: str | None
    optimal_name: str | None
    heuristic_url: str | None
    heuristic_name: str | None
    bounds_url: str | None
    bounds_name: str | None
    filename_pattern: re.Pattern[str]


@dataclass
class InstanceData:
    path: Path
    n: int
    resource_count: int
    durations: list[int]
    resources: list[list[int]]
    capacities: list[int]
    successors: list[list[int]]
    predecessors: list[list[int]]


DATASET_SPECS: dict[str, DatasetSpec] = {
    "j10": DatasetSpec(
        name="j10",
        file_glob="*.SCH",
        format="sch",
        instances_dir=ROOT / "sm_j10",
        archive_url=None,
        archive_name=None,
        optimal_url=None,
        optimal_name=None,
        heuristic_url=None,
        heuristic_name=None,
        bounds_url=None,
        bounds_name=None,
        filename_pattern=re.compile(r"^PSP(\d+)\.SCH$"),
    ),
    "j20": DatasetSpec(
        name="j20",
        file_glob="*.SCH",
        format="sch",
        instances_dir=ROOT / "sm_j20",
        archive_url=None,
        archive_name=None,
        optimal_url=None,
        optimal_name=None,
        heuristic_url=None,
        heuristic_name=None,
        bounds_url=None,
        bounds_name=None,
        filename_pattern=re.compile(r"^PSP(\d+)\.SCH$"),
    ),
    "j30": DatasetSpec(
        name="j30",
        file_glob="*.sm",
        format="sm",
        instances_dir=DATASETS_ROOT / "j30" / "instances",
        archive_url="https://www.om-db.wi.tum.de/psplib/files/j30.sm.zip",
        archive_name="j30.sm.zip",
        optimal_url="https://www.om-db.wi.tum.de/psplib/files/j30opt.sm",
        optimal_name="j30opt.sm",
        heuristic_url="https://www.om-db.wi.tum.de/psplib/files/j30hrs.sm",
        heuristic_name="j30hrs.sm",
        bounds_url=None,
        bounds_name=None,
        filename_pattern=re.compile(r"^j30(\d+)_(\d+)\.sm$"),
    ),
    "j60": DatasetSpec(
        name="j60",
        file_glob="*.sm",
        format="sm",
        instances_dir=DATASETS_ROOT / "j60" / "instances",
        archive_url="https://www.om-db.wi.tum.de/psplib/files/j60.sm.zip",
        archive_name="j60.sm.zip",
        optimal_url=None,
        optimal_name=None,
        heuristic_url="https://www.om-db.wi.tum.de/psplib/files/j60hrs.sm",
        heuristic_name="j60hrs.sm",
        bounds_url="https://www.om-db.wi.tum.de/psplib/files/j60lb.sm",
        bounds_name="j60lb.sm",
        filename_pattern=re.compile(r"^j60(\d+)_(\d+)\.sm$"),
    ),
    "j90": DatasetSpec(
        name="j90",
        file_glob="*.sm",
        format="sm",
        instances_dir=DATASETS_ROOT / "j90" / "instances",
        archive_url="https://www.om-db.wi.tum.de/psplib/files/j90.sm.zip",
        archive_name="j90.sm.zip",
        optimal_url=None,
        optimal_name=None,
        heuristic_url="https://www.om-db.wi.tum.de/psplib/files/j90hrs.sm",
        heuristic_name="j90hrs.sm",
        bounds_url="https://www.om-db.wi.tum.de/psplib/files/j90lb.sm",
        bounds_name="j90lb.sm",
        filename_pattern=re.compile(r"^j90(\d+)_(\d+)\.sm$"),
    ),
    "j120": DatasetSpec(
        name="j120",
        file_glob="*.sm",
        format="sm",
        instances_dir=DATASETS_ROOT / "j120" / "instances",
        archive_url="https://www.om-db.wi.tum.de/psplib/files/j120.sm.zip",
        archive_name="j120.sm.zip",
        optimal_url=None,
        optimal_name=None,
        heuristic_url="https://www.om-db.wi.tum.de/psplib/files/j120hrs.sm",
        heuristic_name="j120hrs.sm",
        bounds_url="https://www.om-db.wi.tum.de/psplib/files/j120lb.sm",
        bounds_name="j120lb.sm",
        filename_pattern=re.compile(r"^j120(\d+)_(\d+)\.sm$"),
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch and benchmark PSPLIB RCPSP datasets.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch_parser = subparsers.add_parser("fetch", help="Download and extract a benchmark dataset.")
    fetch_parser.add_argument("--dataset", choices=sorted(DATASET_SPECS), required=True)
    fetch_parser.add_argument("--force", action="store_true", help="Redownload and reextract files.")

    run_parser = subparsers.add_parser("run", help="Benchmark a solver against a benchmark dataset.")
    run_parser.add_argument("--dataset", choices=sorted(DATASET_SPECS), required=True)
    run_parser.add_argument("--solver", required=True, help="Path to the solver executable.")
    run_parser.add_argument("--build-cmd", help="Optional shell command to build the solver before benchmarking.")
    run_parser.add_argument("--timeout", type=float, default=30.0, help="Per-instance timeout in seconds.")
    run_parser.add_argument("--limit", type=int, default=0, help="Only run the first N instances.")
    run_parser.add_argument("--match", help="Only run instances whose filename contains this substring.")
    run_parser.add_argument(
        "--output-dir",
        type=Path,
        default=RESULTS_ROOT / "j30",
        help="Directory for CSV, JSON, and failure artifacts.",
    )
    run_parser.add_argument(
        "--keep-all-artifacts",
        action="store_true",
        help="Store stdout/stderr artifacts for every instance instead of only failures.",
    )

    return parser.parse_args()


def download_file(url: str, destination: Path, force: bool) -> None:
    if destination.exists() and not force:
        print(f"reuse {destination}")
        return

    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = destination.with_suffix(destination.suffix + ".tmp")
    print(f"download {url} -> {destination}")
    with urllib.request.urlopen(url) as response, tmp_path.open("wb") as out:
        shutil.copyfileobj(response, out)
    tmp_path.replace(destination)


def extract_zip(archive_path: Path, destination: Path, force: bool) -> None:
    marker_path = destination / ".extracted"
    if marker_path.exists() and not force:
        print(f"reuse extracted {destination}")
        return

    if destination.exists() and force:
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)

    print(f"extract {archive_path} -> {destination}")
    with zipfile.ZipFile(archive_path) as archive:
        archive.extractall(destination)

    marker_path.write_text(f"source={archive_path.name}\n", encoding="utf-8")


def fetch_dataset(dataset_name: str, force: bool) -> None:
    spec = DATASET_SPECS[dataset_name]
    if spec.archive_url is None or spec.archive_name is None:
        raise SystemExit(f"dataset {spec.name} is local to this repo and does not support fetch")

    base_dir = DATASETS_ROOT / spec.name
    raw_dir = base_dir / "raw"
    instances_dir = spec.instances_dir

    download_file(spec.archive_url, raw_dir / spec.archive_name, force)
    if spec.optimal_url and spec.optimal_name:
        download_file(spec.optimal_url, raw_dir / spec.optimal_name, force)
    if spec.heuristic_url and spec.heuristic_name:
        download_file(spec.heuristic_url, raw_dir / spec.heuristic_name, force)
    if spec.bounds_url and spec.bounds_name:
        download_file(spec.bounds_url, raw_dir / spec.bounds_name, force)
    extract_zip(raw_dir / spec.archive_name, instances_dir, force)


def parse_reference_table(path: Path) -> dict[tuple[int, int], int]:
    table: dict[tuple[int, int], int] = {}
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = re.match(r"^\s*(\d+)\s+(\d+)\s+(\d+)\b", raw_line)
        if match:
            key = (int(match.group(1)), int(match.group(2)))
            table[key] = int(match.group(3))
    return table


def parse_bounds_table(path: Path) -> dict[tuple[int, int], dict[str, int | bool]]:
    table: dict[tuple[int, int], dict[str, int | bool]] = {}
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = re.match(r"^\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*(\*)?", raw_line)
        if not match:
            continue
        key = (int(match.group(1)), int(match.group(2)))
        table[key] = {
            "upper_bound": int(match.group(3)),
            "lower_bound": int(match.group(4)),
            "exact": bool(match.group(5)),
        }
    return table


def parse_instance_name(spec: DatasetSpec, path: Path) -> tuple[int, int]:
    match = spec.filename_pattern.fullmatch(path.name)
    if not match:
        raise ValueError(f"unsupported instance filename: {path.name}")
    if match.lastindex == 1:
        return 0, int(match.group(1))
    return int(match.group(1)), int(match.group(2))


def sorted_instances(spec: DatasetSpec, instances_dir: Path) -> list[Path]:
    candidates = list(instances_dir.glob(spec.file_glob))
    return sorted(candidates, key=lambda path: parse_instance_name(spec, path))


def parse_sm_instance(path: Path) -> InstanceData:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()

    total_jobs = None
    renewable_resources = None
    precedence_start = None
    requests_start = None
    availability_start = None

    for index, line in enumerate(lines):
        if "jobs (incl. supersource/sink )" in line:
            total_jobs = int(line.split(":", 1)[1].strip())
        elif "- renewable" in line and "nonrenewable" not in line:
            renewable_resources = int(line.split(":", 1)[1].split()[0])
        elif "PRECEDENCE RELATIONS:" in line:
            precedence_start = index + 2
        elif "REQUESTS/DURATIONS:" in line:
            requests_start = index + 3
        elif "RESOURCEAVAILABILITIES:" in line:
            availability_start = index + 2

    if None in (total_jobs, renewable_resources, precedence_start, requests_start, availability_start):
        raise ValueError(f"could not parse PSPLIB sections from {path}")

    total_jobs = int(total_jobs)
    renewable_resources = int(renewable_resources)
    n = total_jobs - 2

    durations = [0] * total_jobs
    resources = [[0] * renewable_resources for _ in range(total_jobs)]
    successors = [[] for _ in range(total_jobs)]

    for line in lines[precedence_start:]:
        stripped = line.strip()
        if not stripped or stripped.startswith("*"):
            break
        fields = stripped.split()
        job_nr = int(fields[0]) - 1
        successor_count = int(fields[2])
        successors[job_nr] = [int(value) - 1 for value in fields[3 : 3 + successor_count]]

    for line in lines[requests_start:]:
        stripped = line.strip()
        if not stripped or stripped.startswith("*"):
            break
        fields = stripped.split()
        job_nr = int(fields[0]) - 1
        durations[job_nr] = int(fields[2])
        resources[job_nr] = [int(value) for value in fields[3 : 3 + renewable_resources]]

    capacities = [int(value) for value in lines[availability_start].split()]
    predecessors = [[] for _ in range(total_jobs)]
    for source, targets in enumerate(successors):
        for target in targets:
            predecessors[target].append(source)

    return InstanceData(
        path=path,
        n=n,
        resource_count=renewable_resources,
        durations=durations,
        resources=resources,
        capacities=capacities,
        successors=successors,
        predecessors=predecessors,
    )


def parse_sch_instance(path: Path) -> InstanceData:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    first = lines[0].split()
    n = int(first[0])
    resource_count = int(first[1])
    total_jobs = n + 2

    durations = [0] * total_jobs
    resources = [[0] * resource_count for _ in range(total_jobs)]
    successors = [[] for _ in range(total_jobs)]
    predecessors = [[] for _ in range(total_jobs)]

    precedence_lines = lines[1 : 1 + total_jobs]
    request_lines = lines[1 + total_jobs : 1 + 2 * total_jobs]
    capacity_line = lines[1 + 2 * total_jobs]

    for line in precedence_lines:
        fields = line.split()
        act_id = int(fields[0])
        has_bracket_lag = any(token.startswith("[") and token.endswith("]") for token in fields)

        if has_bracket_lag:
            successor_count = int(fields[2])
            successor_start = 3
        elif len(fields) >= 2 and len(fields) == 2 + int(fields[1]):
            successor_count = int(fields[1])
            successor_start = 2
        elif len(fields) >= 3 and len(fields) == 3 + int(fields[2]):
            successor_count = int(fields[2])
            successor_start = 3
        elif len(fields) >= 3 and int(fields[1]) == 1:
            successor_count = int(fields[2])
            successor_start = 3
        else:
            raise ValueError(f"unrecognised .SCH precedence line in {path.name}: {line!r}")

        successor_ids = [int(value) for value in fields[successor_start : successor_start + successor_count]]
        lag_tokens = fields[successor_start + successor_count :]
        for index, successor_id in enumerate(successor_ids):
            if index >= len(lag_tokens):
                lag = 0
            else:
                lag_token = lag_tokens[index]
                lag = int(lag_token[1:-1]) if lag_token.startswith("[") and lag_token.endswith("]") else 0
            if lag >= 0:
                successors[act_id].append(successor_id)
                predecessors[successor_id].append(act_id)

    for line in request_lines:
        fields = line.split()
        act_id = int(fields[0])
        if len(fields) == resource_count + 2:
            duration_index = 1
            resource_start = 2
        elif len(fields) == resource_count + 3:
            duration_index = 2
            resource_start = 3
        else:
            raise ValueError(f"unrecognised .SCH duration/resource line in {path.name}: {line!r}")

        durations[act_id] = int(fields[duration_index])
        resources[act_id] = [int(value) for value in fields[resource_start : resource_start + resource_count]]

    capacities = [int(value) for value in capacity_line.split()[:resource_count]]

    return InstanceData(
        path=path,
        n=n,
        resource_count=resource_count,
        durations=durations,
        resources=resources,
        capacities=capacities,
        successors=successors,
        predecessors=predecessors,
    )


def parse_instance(spec: DatasetSpec, path: Path) -> InstanceData:
    if spec.format == "sm":
        return parse_sm_instance(path)
    if spec.format == "sch":
        return parse_sch_instance(path)
    raise ValueError(f"unsupported dataset format: {spec.format}")


def run_build_command(build_cmd: str) -> None:
    print(f"build {build_cmd}")
    completed = subprocess.run(build_cmd, shell=True, cwd=ROOT)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def parse_solver_output(instance: InstanceData, stdout_text: str) -> tuple[list[int] | None, str | None]:
    lines = [line.strip() for line in stdout_text.splitlines() if line.strip()]
    if len(lines) != instance.n:
        return None, f"expected {instance.n} start times, got {len(lines)}"

    start_times = [0] * (instance.n + 2)
    for index, line in enumerate(lines, start=1):
        try:
            value = int(line)
        except ValueError:
            return None, f"non-integer start time on line {index}: {line!r}"
        if value < 0:
            return None, f"negative start time on line {index}: {value}"
        start_times[index] = value

    sink_index = instance.n + 1
    if instance.predecessors[sink_index]:
        start_times[sink_index] = max(
            start_times[pred] + instance.durations[pred] for pred in instance.predecessors[sink_index]
        )

    return start_times, None


def validate_schedule(instance: InstanceData, start_times: list[int]) -> tuple[bool, str | None, int]:
    for source, targets in enumerate(instance.successors):
        finish = start_times[source] + instance.durations[source]
        for target in targets:
            if start_times[target] < finish:
                return False, f"precedence violation {source}->{target}", 0

    makespan = max(
        (start_times[job] + instance.durations[job] for job in range(1, instance.n + 1)),
        default=0,
    )

    usage = [[0] * instance.resource_count for _ in range(makespan)]
    for job in range(1, instance.n + 1):
        start = start_times[job]
        finish = start + instance.durations[job]
        for time_slot in range(start, finish):
            for resource_id in range(instance.resource_count):
                usage[time_slot][resource_id] += instance.resources[job][resource_id]

    for time_slot, resource_usage in enumerate(usage):
        for resource_id, used in enumerate(resource_usage):
            if used > instance.capacities[resource_id]:
                return (
                    False,
                    f"resource violation t={time_slot} r={resource_id + 1}: {used}>{instance.capacities[resource_id]}",
                    makespan,
                )

    return True, None, makespan


def parse_reported_makespan(stderr_text: str) -> int | None:
    match = re.search(r"Makespan:\s*(\d+)", stderr_text)
    if not match:
        return None
    return int(match.group(1))


def ensure_dataset_ready(
    spec: DatasetSpec,
) -> tuple[
    Path,
    dict[tuple[int, int], int] | None,
    dict[tuple[int, int], int] | None,
    dict[tuple[int, int], dict[str, int | bool]] | None,
]:
    instances_dir = spec.instances_dir
    if not instances_dir.exists():
        if spec.archive_url is None:
            raise SystemExit(f"dataset {spec.name} not found under {instances_dir}")
        raise SystemExit(
            f"dataset {spec.name} not found under {instances_dir}. Run `python3 scripts/benchmark_rcpsp.py fetch --dataset {spec.name}` first."
        )

    raw_dir = DATASETS_ROOT / spec.name / "raw"
    optimal = None
    heuristic = None
    bounds = None
    if spec.optimal_name:
        optimal_path = raw_dir / spec.optimal_name
        if optimal_path.exists():
            optimal = parse_reference_table(optimal_path)
    if spec.heuristic_name:
        heuristic_path = raw_dir / spec.heuristic_name
        if heuristic_path.exists():
            heuristic = parse_reference_table(heuristic_path)
    if spec.bounds_name:
        bounds_path = raw_dir / spec.bounds_name
        if bounds_path.exists():
            bounds = parse_bounds_table(bounds_path)
    return instances_dir, optimal, heuristic, bounds


def write_artifacts(base_dir: Path, instance_name: str, stdout_text: str, stderr_text: str) -> None:
    base_dir.mkdir(parents=True, exist_ok=True)
    (base_dir / f"{instance_name}.stdout.txt").write_text(stdout_text, encoding="utf-8")
    (base_dir / f"{instance_name}.stderr.txt").write_text(stderr_text, encoding="utf-8")


def compute_gap(makespan: int | None, reference: int | None) -> float | None:
    if makespan is None or reference in (None, 0):
        return None
    return 100.0 * (makespan - reference) / reference


def compute_quality_score(makespan: int | None, reference: int | None) -> float | None:
    if makespan in (None, 0) or reference is None:
        return None
    return 100.0 * reference / makespan


def summarize(rows: Iterable[dict[str, object]]) -> dict[str, object]:
    row_list = list(rows)
    wall_times = [float(row["wall_time_seconds"]) for row in row_list if row["wall_time_seconds"] is not None]
    best_known_gaps = [float(row["gap_to_best_known_pct"]) for row in row_list if row["gap_to_best_known_pct"] is not None]
    lower_bound_gaps = [float(row["gap_to_lower_bound_pct"]) for row in row_list if row["gap_to_lower_bound_pct"] is not None]
    best_known_quality = [
        float(row["quality_vs_best_known_pct"]) for row in row_list if row["quality_vs_best_known_pct"] is not None
    ]
    exact_quality = [
        float(row["quality_vs_exact_reference_pct"])
        for row in row_list
        if row["quality_vs_exact_reference_pct"] is not None
    ]

    summary = {
        "instance_count": len(row_list),
        "ok_count": sum(1 for row in row_list if row["status"] == "ok"),
        "timeout_count": sum(1 for row in row_list if row["status"] == "timeout"),
        "invalid_count": sum(1 for row in row_list if row["status"] not in {"ok", "timeout"}),
        "exact_reference_match_count": sum(1 for row in row_list if row["matched_exact_reference"] is True),
        "best_known_match_count": sum(1 for row in row_list if row["matched_best_known"] is True),
        "mean_wall_time_seconds": statistics.fmean(wall_times) if wall_times else None,
        "max_wall_time_seconds": max(wall_times) if wall_times else None,
        "mean_gap_to_best_known_pct": statistics.fmean(best_known_gaps) if best_known_gaps else None,
        "max_gap_to_best_known_pct": max(best_known_gaps) if best_known_gaps else None,
        "mean_gap_to_lower_bound_pct": statistics.fmean(lower_bound_gaps) if lower_bound_gaps else None,
        "max_gap_to_lower_bound_pct": max(lower_bound_gaps) if lower_bound_gaps else None,
        "mean_quality_vs_best_known_pct": statistics.fmean(best_known_quality) if best_known_quality else None,
        "median_quality_vs_best_known_pct": statistics.median(best_known_quality) if best_known_quality else None,
        "min_quality_vs_best_known_pct": min(best_known_quality) if best_known_quality else None,
        "mean_quality_vs_exact_reference_pct": statistics.fmean(exact_quality) if exact_quality else None,
        "median_quality_vs_exact_reference_pct": statistics.median(exact_quality) if exact_quality else None,
    }
    return summary


def benchmark_solver(args: argparse.Namespace) -> None:
    spec = DATASET_SPECS[args.dataset]
    instances_dir, optimal_refs, heuristic_refs, bound_refs = ensure_dataset_ready(spec)

    solver_path = (ROOT / args.solver).resolve() if not Path(args.solver).is_absolute() else Path(args.solver)
    if args.build_cmd:
        run_build_command(args.build_cmd)
    if not solver_path.exists():
        raise SystemExit(f"solver not found: {solver_path}")

    output_dir = args.output_dir
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    if output_dir == RESULTS_ROOT / "j30":
        output_dir = RESULTS_ROOT / spec.name
    failures_dir = output_dir / "failures"
    output_dir.mkdir(parents=True, exist_ok=True)

    instances = sorted_instances(spec, instances_dir)
    if args.match:
        instances = [path for path in instances if args.match in path.name]
    if args.limit > 0:
        instances = instances[: args.limit]

    if not instances:
        raise SystemExit("no instances matched the requested selection")

    rows: list[dict[str, object]] = []

    for index, instance_path in enumerate(instances, start=1):
        param, inst = parse_instance_name(spec, instance_path)
        instance = parse_instance(spec, instance_path)

        start_time = time.perf_counter()
        timeout = False
        stdout_text = ""
        stderr_text = ""
        return_code = None
        status = "ok"
        status_detail = ""
        computed_makespan = None
        reported_makespan = None

        try:
            completed = subprocess.run(
                [str(solver_path), str(instance_path)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=args.timeout,
            )
            return_code = completed.returncode
            stdout_text = completed.stdout
            stderr_text = completed.stderr
        except subprocess.TimeoutExpired as exc:
            timeout = True
            stdout_text = exc.stdout or ""
            stderr_text = exc.stderr or ""

        wall_time = time.perf_counter() - start_time
        reported_makespan = parse_reported_makespan(stderr_text)

        matched_optimal = None
        matched_heuristic = None
        precedence_ok = None
        resources_ok = None
        parse_error = None

        if timeout:
            status = "timeout"
            status_detail = f"exceeded {args.timeout:.2f}s"
        elif return_code != 0:
            status = "run_error"
            status_detail = f"solver exited with code {return_code}"
        else:
            start_times, parse_error = parse_solver_output(instance, stdout_text)
            if start_times is None:
                status = "invalid_output"
                status_detail = parse_error or "unable to parse solver output"
            else:
                valid, validation_error, computed_makespan = validate_schedule(instance, start_times)
                precedence_ok = False if validation_error and validation_error.startswith("precedence") else valid
                resources_ok = False if validation_error and validation_error.startswith("resource") else valid
                if not valid:
                    status = "invalid_schedule"
                    status_detail = validation_error or "schedule validation failed"
                elif reported_makespan is not None and reported_makespan != computed_makespan:
                    status = "invalid_output"
                    status_detail = f"reported makespan {reported_makespan} != computed makespan {computed_makespan}"

        optimal_value = optimal_refs.get((param, inst)) if optimal_refs else None
        heuristic_value = heuristic_refs.get((param, inst)) if heuristic_refs else None
        bound_entry = bound_refs.get((param, inst)) if bound_refs else None
        lower_bound = int(bound_entry["lower_bound"]) if bound_entry else None
        upper_bound = int(bound_entry["upper_bound"]) if bound_entry else None
        exact_from_bounds = bool(bound_entry["exact"]) if bound_entry else False

        best_known_value = optimal_value if optimal_value is not None else upper_bound if upper_bound is not None else heuristic_value
        exact_value = optimal_value if optimal_value is not None else lower_bound if exact_from_bounds else None

        gap_to_best_known = compute_gap(computed_makespan, best_known_value)
        gap_to_lower_bound = compute_gap(computed_makespan, lower_bound)
        quality_vs_best_known = compute_quality_score(computed_makespan, best_known_value)
        quality_vs_exact_reference = compute_quality_score(computed_makespan, exact_value)

        if computed_makespan is not None and exact_value is not None:
            matched_optimal = computed_makespan == exact_value
        if computed_makespan is not None and best_known_value is not None:
            matched_heuristic = computed_makespan == best_known_value

        row = {
            "dataset": spec.name,
            "file": str(instance_path.relative_to(ROOT)),
            "param": param,
            "instance": inst,
            "status": status,
            "status_detail": status_detail,
            "return_code": return_code,
            "timed_out": timeout,
            "wall_time_seconds": round(wall_time, 6),
            "reported_makespan": reported_makespan,
            "computed_makespan": computed_makespan,
            "exact_reference_makespan": exact_value,
            "best_known_makespan": best_known_value,
            "heuristic_makespan": heuristic_value,
            "upper_bound": upper_bound,
            "lower_bound": lower_bound,
            "gap_to_best_known_pct": round(gap_to_best_known, 6) if gap_to_best_known is not None else None,
            "gap_to_lower_bound_pct": round(gap_to_lower_bound, 6) if gap_to_lower_bound is not None else None,
            "quality_vs_best_known_pct": round(quality_vs_best_known, 6) if quality_vs_best_known is not None else None,
            "quality_vs_exact_reference_pct": (
                round(quality_vs_exact_reference, 6) if quality_vs_exact_reference is not None else None
            ),
            "matched_exact_reference": matched_optimal,
            "matched_best_known": matched_heuristic,
            "precedence_ok": precedence_ok,
            "resources_ok": resources_ok,
            "stdout_line_count": len([line for line in stdout_text.splitlines() if line.strip()]),
        }
        rows.append(row)

        should_write_artifacts = args.keep_all_artifacts or status != "ok"
        if should_write_artifacts:
            write_artifacts(failures_dir, instance_path.stem, stdout_text, stderr_text)

        summary_bits = [f"[{index}/{len(instances)}]", instance_path.name, status, f"{wall_time:.3f}s"]
        if computed_makespan is not None:
            summary_bits.append(f"mksp={computed_makespan}")
        if best_known_value is not None and gap_to_best_known is not None:
            summary_bits.append(f"gap_best={gap_to_best_known:.2f}%")
        if quality_vs_best_known is not None:
            summary_bits.append(f"quality={quality_vs_best_known:.2f}%")
        print(" | ".join(summary_bits))

    csv_path = output_dir / "results.csv"
    json_path = output_dir / "summary.json"

    fieldnames = list(rows[0].keys())
    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    summary = summarize(rows)
    with json_path.open("w", encoding="utf-8") as json_file:
        json.dump(summary, json_file, indent=2, sort_keys=True)
        json_file.write("\n")

    print()
    print(json.dumps(summary, indent=2, sort_keys=True))
    print(f"wrote {csv_path}")
    print(f"wrote {json_path}")

    if summary["timeout_count"] or summary["invalid_count"]:
        raise SystemExit(1)


def main() -> None:
    args = parse_args()
    if args.command == "fetch":
        fetch_dataset(args.dataset, args.force)
    elif args.command == "run":
        benchmark_solver(args)
    else:
        raise SystemExit(f"unsupported command: {args.command}")


if __name__ == "__main__":
    main()
