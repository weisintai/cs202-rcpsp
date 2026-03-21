from scripts.autoresearch_lib import compare_summaries, summarize_autoresearch


def _run(
    dataset: str,
    time_limit: float,
    *,
    feasible: int,
    infeasible: int,
    unknown: int,
    over_budget: int,
    exact_match_rate: float,
    avg_exact_ratio_to_reference: float,
    false_infeasible: int = 0,
) -> dict:
    return {
        "dataset": dataset,
        "time_limit": time_limit,
        "benchmark_summary": {
            "feasible": feasible,
            "infeasible": infeasible,
            "unknown": unknown,
            "over_budget": over_budget,
            "avg_ratio": 1.0,
            "avg_runtime_seconds": 0.1,
            "max_runtime_seconds": 0.1,
        },
        "compare_summary": {
            "exact_cases": feasible,
            "matched_exact": int(round(feasible * exact_match_rate)),
            "exact_match_rate": exact_match_rate,
            "avg_exact_ratio_to_reference": avg_exact_ratio_to_reference,
            "false_infeasible": false_infeasible,
            "unknown_against_known_reference": unknown,
            "matched_best_known_upper": 0,
            "better_than_best_known": 0,
        },
        "benchmark_output": "missing.json",
        "compare_output": "missing_compare.json",
    }


def test_autoresearch_summary_marks_targets_passed() -> None:
    summary = {
        "runs": [
            _run("sm_j10", 1.0, feasible=187, infeasible=83, unknown=0, over_budget=0, exact_match_rate=1.0, avg_exact_ratio_to_reference=1.0),
            _run("sm_j20", 1.0, feasible=184, infeasible=79, unknown=2, over_budget=0, exact_match_rate=0.86, avg_exact_ratio_to_reference=1.014),
            _run("sm_j30", 0.1, feasible=170, infeasible=79, unknown=15, over_budget=0, exact_match_rate=0.60, avg_exact_ratio_to_reference=1.03),
            _run("testset_ubo20", 0.1, feasible=70, infeasible=19, unknown=0, over_budget=0, exact_match_rate=0.70, avg_exact_ratio_to_reference=1.01),
            _run("testset_ubo50", 0.1, feasible=51, infeasible=14, unknown=15, over_budget=0, exact_match_rate=0.45, avg_exact_ratio_to_reference=1.03),
        ]
    }

    evaluation = summarize_autoresearch(summary)

    assert evaluation["passes_all_targets"]
    assert not evaluation["failed_checks"]
    assert evaluation["score"] > 0.0


def test_autoresearch_comparison_detects_regression() -> None:
    baseline = {"evaluation": {"score": 500.0, "passes_all_targets": True}}
    current = {"score": 480.0, "passes_all_targets": False}

    comparison = compare_summaries(current, baseline["evaluation"])

    assert comparison["delta"] == -20.0
    assert not comparison["better"]
    assert comparison["baseline_passes_all_targets"]
    assert not comparison["current_passes_all_targets"]


def test_autoresearch_summary_flags_over_budget_regression() -> None:
    summary = {
        "runs": [
            _run("sm_j10", 1.0, feasible=187, infeasible=83, unknown=0, over_budget=0, exact_match_rate=1.0, avg_exact_ratio_to_reference=1.0),
            _run("sm_j20", 1.0, feasible=184, infeasible=79, unknown=2, over_budget=3, exact_match_rate=0.86, avg_exact_ratio_to_reference=1.014),
        ]
    }

    evaluation = summarize_autoresearch(summary)

    assert not evaluation["passes_all_targets"]
    assert any(check["field"] == "over_budget" and not check["passed"] for check in evaluation["failed_checks"])
    assert evaluation["score_components"]["over_budget_penalty"] == -300.0
