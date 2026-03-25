import threading

from scripts import guardrails_lib


def test_run_guardrail_suite_jobs_zero_runs_all_selected_cases_in_parallel(
    monkeypatch,
    tmp_path,
) -> None:
    preset = "parallel_test"
    cases = (
        guardrails_lib.GuardrailCase("dataset_a", 0.1),
        guardrails_lib.GuardrailCase("dataset_b", 0.2),
    )
    monkeypatch.setitem(guardrails_lib.PRESETS, preset, cases)
    monkeypatch.setattr(guardrails_lib, "build_run_metadata", lambda: {"test": True})

    barrier = threading.Barrier(len(cases))

    def fake_run_guardrail_case(
        *,
        case,
        backend,
        seed,
        max_restarts,
        heuristic_args,
        resolved_output_dir,
        dry_run,
    ) -> dict:
        barrier.wait(timeout=1.0)
        return {
            "label": f"{case.dataset}@{case.time_limit:.1f}s",
            "dataset": case.dataset,
            "time_limit": case.time_limit,
            "benchmark_summary": {},
            "compare_summary": {},
            "benchmark_output": str(resolved_output_dir / f"{case.dataset}.json"),
            "compare_output": str(resolved_output_dir / f"{case.dataset}_compare.json"),
            "benchmark_command": [backend, str(seed), str(max_restarts)],
            "compare_command": [str(bool(heuristic_args)), str(dry_run)],
        }

    monkeypatch.setattr(
        guardrails_lib,
        "_run_guardrail_case",
        fake_run_guardrail_case,
    )

    result = guardrails_lib.run_guardrail_suite(
        backend="cp",
        preset=preset,
        output_dir=tmp_path,
        jobs=0,
        dry_run=True,
    )

    assert result["jobs"] == len(cases)
    assert [run["dataset"] for run in result["summary"]["runs"]] == [
        "dataset_a",
        "dataset_b",
    ]
