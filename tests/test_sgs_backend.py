import random
import time

from rcpsp import parse_sch, solve_sgs
from rcpsp.temporal import longest_feasible_starts
from rcpsp.sgs.adapter import adapt_instance
from rcpsp.sgs.restarts import run_restart_batch
from rcpsp.validate import validate_schedule


def test_sgs_adapter_splits_negative_lags_into_max_lags() -> None:
    instance = parse_sch("benchmarks/data/sm_j10/PSP1.SCH")
    sgs_instance = adapt_instance(instance)

    activity_one = sgs_instance.activities[1]
    assert (8, 8) in {(arc.activity, arc.lag) for arc in activity_one.min_successors}
    assert (8, 22) in {(arc.activity, arc.lag) for arc in activity_one.max_successors}
    assert sgs_instance.topo_order[0] == instance.source
    assert sgs_instance.topo_order[-1] == instance.sink


def test_sgs_solver_finds_feasible_schedule_on_small_instance() -> None:
    instance = parse_sch("benchmarks/data/sm_j10/PSP1.SCH")
    result = solve_sgs(instance, time_limit=0.5, seed=0)

    assert result.status == "feasible"
    assert result.schedule is not None
    assert validate_schedule(instance, result.schedule) == []


def test_sgs_restart_batch_finds_schedule_on_small_instance() -> None:
    instance = parse_sch("benchmarks/data/sm_j10/PSP1.SCH")
    sgs_instance = adapt_instance(instance)
    temporal_lower = longest_feasible_starts(instance)

    schedule, stats = run_restart_batch(
        sgs_instance,
        temporal_lower,
        deadline=time.perf_counter() + 0.5,
        rng=random.Random(0),
    )

    assert schedule is not None
    assert stats.restarts >= 1
    assert validate_schedule(instance, schedule) == []


def test_sgs_solver_reports_obvious_pairwise_infeasibility() -> None:
    instance = parse_sch("benchmarks/data/sm_j10/PSP108.SCH")
    result = solve_sgs(instance, time_limit=0.1, seed=0)

    assert result.status == "infeasible"
    assert result.schedule is None
