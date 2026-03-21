from main import _enforce_runtime_limit
from rcpsp.models import Schedule, SolveResult


def test_enforce_runtime_limit_marks_late_solution_unknown() -> None:
    result = SolveResult(
        instance_name="PSP48",
        status="feasible",
        schedule=Schedule(start_times=(0, 1), makespan=1),
        runtime_seconds=1.2,
        temporal_lower_bound=1,
        restarts=3,
        metadata={"seed": 0, "time_limit": 1.0},
    )

    limited = _enforce_runtime_limit(result, time_limit=1.0)

    assert limited.status == "unknown"
    assert limited.schedule is None
    assert limited.metadata["original_status"] == "feasible"
    assert limited.metadata["late_solution"] == 1


def test_enforce_runtime_limit_keeps_small_overhead() -> None:
    result = SolveResult(
        instance_name="PSP48",
        status="feasible",
        schedule=Schedule(start_times=(0, 1), makespan=1),
        runtime_seconds=1.005,
        temporal_lower_bound=1,
        restarts=3,
        metadata={"seed": 0, "time_limit": 1.0},
    )

    limited = _enforce_runtime_limit(result, time_limit=1.0)

    assert limited.status == "feasible"
    assert limited.schedule is not None
