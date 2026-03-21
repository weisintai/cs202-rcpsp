from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def case_label(dataset: str, time_limit: float) -> str:
    return f"{dataset}@{time_limit:.1f}s"


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * (q / 100.0)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    fraction = rank - low
    return ordered[low] + (ordered[high] - ordered[low]) * fraction


def _load_runtime_quantiles(run: dict[str, Any]) -> tuple[float | None, float | None]:
    benchmark_output = Path(run["benchmark_output"])
    if not benchmark_output.exists():
        return None, None
    payload = json.loads(benchmark_output.read_text(encoding="utf-8"))
    runtimes = [row["runtime_seconds"] for row in payload.get("results", []) if row.get("runtime_seconds") is not None]
    return _percentile(runtimes, 95.0), _percentile(runtimes, 99.0)


def build_case_metrics(summary: dict[str, Any]) -> dict[str, dict[str, Any]]:
    cases: dict[str, dict[str, Any]] = {}
    for run in summary["runs"]:
        benchmark_summary = run["benchmark_summary"]
        compare_summary = run["compare_summary"]
        p95_runtime, p99_runtime = _load_runtime_quantiles(run)
        label = case_label(run["dataset"], run["time_limit"])
        cases[label] = {
            "dataset": run["dataset"],
            "time_limit": run["time_limit"],
            "feasible": benchmark_summary.get("feasible"),
            "infeasible": benchmark_summary.get("infeasible"),
            "unknown": benchmark_summary.get("unknown"),
            "avg_ratio": benchmark_summary.get("avg_ratio"),
            "avg_runtime_seconds": benchmark_summary.get("avg_runtime_seconds"),
            "max_runtime_seconds": benchmark_summary.get("max_runtime_seconds"),
            "over_budget": benchmark_summary.get("over_budget"),
            "p95_runtime_seconds": p95_runtime,
            "p99_runtime_seconds": p99_runtime,
            "exact_cases": compare_summary.get("exact_cases"),
            "matched_exact": compare_summary.get("matched_exact"),
            "exact_match_rate": compare_summary.get("exact_match_rate"),
            "avg_exact_ratio_to_reference": compare_summary.get("avg_exact_ratio_to_reference"),
            "false_infeasible": compare_summary.get("false_infeasible"),
            "unknown_against_known_reference": compare_summary.get("unknown_against_known_reference"),
            "matched_best_known_upper": compare_summary.get("matched_best_known_upper"),
            "better_than_best_known": compare_summary.get("better_than_best_known"),
        }
    return cases


def _metric_value(cases: dict[str, dict[str, Any]], label: str, field: str, default: float = 0.0) -> float:
    value = cases.get(label, {}).get(field)
    if value is None:
        return default
    return float(value)


def _has_metric(cases: dict[str, dict[str, Any]], label: str, field: str) -> bool:
    return label in cases and cases[label].get(field) is not None


def build_target_checks(cases: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    raw_checks = (
        ("sm_j10@1.0s", "exact_match_rate", ">=", 1.0, "Keep `sm_j10 @ 1.0s` at 100% exact-match"),
        ("sm_j10@1.0s", "unknown", "<=", 0.0, "Keep `sm_j10 @ 1.0s` unknown count at 0"),
        ("sm_j10@1.0s", "over_budget", "<=", 0.0, "Keep `sm_j10 @ 1.0s` over-budget count at 0"),
        ("sm_j20@1.0s", "exact_match_rate", ">=", 0.85, "Push `sm_j20 @ 1.0s` exact-match rate to at least 85%"),
        (
            "sm_j20@1.0s",
            "avg_exact_ratio_to_reference",
            "<=",
            1.015,
            "Reduce `sm_j20 @ 1.0s` average exact-reference ratio to 1.015 or below",
        ),
        ("sm_j20@1.0s", "unknown", "<=", 2.0, "Drive `sm_j20 @ 1.0s` unknown count down to at most 2"),
        ("sm_j20@1.0s", "over_budget", "<=", 0.0, "Drive `sm_j20 @ 1.0s` over-budget count down to 0"),
        ("sm_j30@0.1s", "exact_match_rate", ">=", 0.60, "Reach at least 60% exact-match on `sm_j30 @ 0.1s`"),
        ("sm_j30@0.1s", "unknown", "<=", 15.0, "Keep `sm_j30 @ 0.1s` unknown count at or below 15"),
        ("sm_j30@0.1s", "over_budget", "<=", 0.0, "Keep `sm_j30 @ 0.1s` over-budget count at 0"),
        ("testset_ubo20@0.1s", "exact_match_rate", ">=", 0.70, "Reach at least 70% exact-match on `testset_ubo20 @ 0.1s`"),
        ("testset_ubo20@0.1s", "unknown", "<=", 0.0, "Keep `testset_ubo20 @ 0.1s` unknown count at 0"),
        ("testset_ubo20@0.1s", "over_budget", "<=", 0.0, "Keep `testset_ubo20 @ 0.1s` over-budget count at 0"),
        ("testset_ubo50@0.1s", "exact_match_rate", ">=", 0.45, "Reach at least 45% exact-match on `testset_ubo50 @ 0.1s`"),
        ("testset_ubo50@0.1s", "unknown", "<=", 15.0, "Keep `testset_ubo50 @ 0.1s` unknown count at or below 15"),
        ("testset_ubo50@0.1s", "over_budget", "<=", 0.0, "Keep `testset_ubo50 @ 0.1s` over-budget count at 0"),
    )

    checks: list[dict[str, Any]] = []
    for label, field, operator, target, description in raw_checks:
        if not _has_metric(cases, label, field):
            checks.append(
                {
                    "case": label,
                    "field": field,
                    "operator": operator,
                    "target": target,
                    "actual": None,
                    "passed": True,
                    "skipped": True,
                    "description": description,
                }
            )
            continue
        actual = _metric_value(cases, label, field)
        if operator == ">=":
            passed = actual >= target
        else:
            passed = actual <= target
        checks.append(
            {
                "case": label,
                "field": field,
                "operator": operator,
                "target": target,
                "actual": actual,
                "passed": passed,
                "skipped": False,
                "description": description,
            }
        )
    false_infeasible_total = sum(int(metrics.get("false_infeasible") or 0) for metrics in cases.values())
    checks.append(
        {
            "case": "all",
            "field": "false_infeasible",
            "operator": "<=",
            "target": 0.0,
            "actual": float(false_infeasible_total),
            "passed": false_infeasible_total == 0,
            "skipped": False,
            "description": "Never introduce false infeasible classifications",
        }
    )
    return checks


def compute_score(cases: dict[str, dict[str, Any]]) -> dict[str, float]:
    sm_j20_label = "sm_j20@1.0s"
    components = {
        "sm_j20_exact_match": 300.0 * _metric_value(cases, sm_j20_label, "exact_match_rate"),
        "sm_j20_exact_gap_penalty": (
            -4000.0 * max(0.0, _metric_value(cases, sm_j20_label, "avg_exact_ratio_to_reference") - 1.0)
            if _has_metric(cases, sm_j20_label, "avg_exact_ratio_to_reference")
            else 0.0
        ),
        "sm_j20_unknown_penalty": -12.0 * _metric_value(cases, sm_j20_label, "unknown"),
        "sm_j10_exact_match": 120.0 * _metric_value(cases, "sm_j10@1.0s", "exact_match_rate"),
        "sm_j10_unknown_penalty": -25.0 * _metric_value(cases, "sm_j10@1.0s", "unknown"),
        "sm_j30_exact_match": 70.0 * _metric_value(cases, "sm_j30@0.1s", "exact_match_rate"),
        "sm_j30_unknown_penalty": -2.0 * _metric_value(cases, "sm_j30@0.1s", "unknown"),
        "ubo20_exact_match": 60.0 * _metric_value(cases, "testset_ubo20@0.1s", "exact_match_rate"),
        "ubo20_unknown_penalty": -6.0 * _metric_value(cases, "testset_ubo20@0.1s", "unknown"),
        "ubo50_exact_match": 40.0 * _metric_value(cases, "testset_ubo50@0.1s", "exact_match_rate"),
        "ubo50_unknown_penalty": -1.5 * _metric_value(cases, "testset_ubo50@0.1s", "unknown"),
        "over_budget_penalty": -100.0 * sum(_metric_value(cases, label, "over_budget") for label in cases),
        "false_infeasible_penalty": -300.0
        * sum(int(metrics.get("false_infeasible") or 0) for metrics in cases.values()),
    }
    components["total"] = sum(components.values())
    return components


def summarize_autoresearch(summary: dict[str, Any]) -> dict[str, Any]:
    cases = build_case_metrics(summary)
    checks = build_target_checks(cases)
    score_components = compute_score(cases)
    return {
        "score": score_components["total"],
        "score_components": score_components,
        "passes_all_targets": all(check["passed"] for check in checks if not check.get("skipped")),
        "failed_checks": [check for check in checks if not check["passed"]],
        "checks": checks,
        "case_metrics": cases,
    }


def compare_summaries(current: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    delta = float(current["score"]) - float(baseline["score"])
    return {
        "baseline_score": float(baseline["score"]),
        "current_score": float(current["score"]),
        "delta": delta,
        "better": delta > 0.0,
        "baseline_passes_all_targets": bool(baseline["passes_all_targets"]),
        "current_passes_all_targets": bool(current["passes_all_targets"]),
    }
