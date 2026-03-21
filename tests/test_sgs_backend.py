import random
import time
from pathlib import Path

from rcpsp import parse_sch, solve_sgs
from rcpsp.models import Edge, Instance
from rcpsp.temporal import longest_feasible_starts
from rcpsp.sgs.adapter import adapt_instance
from rcpsp.sgs.fbi import forward_backward_improve
from rcpsp.sgs.priorities import (
    incumbent_neighbor_priority_order,
    perturb_priority_order,
    sample_priority_order,
    seed_priority_lists,
    segment_perturb_priority_order,
)
from rcpsp.sgs.restarts import run_restart_batch
from rcpsp.sgs.serial import beam_decode_priority_list, decode_priority_list
from rcpsp.sgs.time_windows import latest_starts_from_upper_bound
from rcpsp.sgs.warm_start import generate_warm_start
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


def test_sgs_priority_generators_return_topological_orders() -> None:
    instance = parse_sch("benchmarks/data/sm_j10/PSP1.SCH")
    sgs_instance = adapt_instance(instance)
    temporal_lower = longest_feasible_starts(instance)
    orders = seed_priority_lists(sgs_instance, temporal_lower)
    orders.append(sample_priority_order(sgs_instance, temporal_lower, random.Random(0)))
    orders.append(perturb_priority_order(sgs_instance, temporal_lower, orders[0], random.Random(1)))
    orders.append(segment_perturb_priority_order(sgs_instance, orders[0], random.Random(2)))
    orders.append(
        incumbent_neighbor_priority_order(
            sgs_instance,
            temporal_lower,
            current_priority=orders[0],
            best_priority=orders[1],
            rng=random.Random(3),
            iteration=5,
        )
    )

    for order in orders:
        indices = {activity: index for index, activity in enumerate(order)}
        for activity in order:
            for predecessor in sgs_instance.activities[activity].min_predecessors:
                if predecessor.activity in indices:
                    assert indices[predecessor.activity] < indices[activity]


def test_sgs_latest_starts_from_upper_bound_respects_sink_bound() -> None:
    instance = parse_sch("benchmarks/data/sm_j10/PSP1.SCH")
    sgs_instance = adapt_instance(instance)
    latest = latest_starts_from_upper_bound(sgs_instance, 26)

    assert latest[instance.source] == 0
    assert latest[instance.sink] == 26
    assert all(value <= 26 for value in latest if value < 10**12)


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


def test_sgs_warm_start_finds_feasible_schedule_on_small_instance() -> None:
    instance = parse_sch("benchmarks/data/sm_j10/PSP1.SCH")
    schedule = generate_warm_start(
        instance,
        rng=random.Random(0),
        deadline=time.perf_counter() + 0.2,
    )

    assert schedule is not None
    assert validate_schedule(instance, schedule) == []


def test_sgs_forward_backward_improve_keeps_schedule_feasible() -> None:
    instance = parse_sch("benchmarks/data/sm_j10/PSP1.SCH")
    sgs_instance = adapt_instance(instance)
    result = solve_sgs(instance, time_limit=0.2, seed=0)

    assert result.schedule is not None
    improved, passes = forward_backward_improve(
        sgs_instance,
        result.schedule,
        deadline=time.perf_counter() + 0.2,
    )

    assert passes >= 0
    assert improved.makespan <= result.schedule.makespan
    assert validate_schedule(instance, improved) == []


def test_sgs_decoder_can_delay_activity_for_unscheduled_max_predecessor() -> None:
    edges = (
        Edge(source=0, target=1, lag=0),
        Edge(source=0, target=2, lag=2),
        Edge(source=2, target=1, lag=-1),
        Edge(source=1, target=3, lag=0),
        Edge(source=2, target=3, lag=0),
    )
    outgoing = (
        (edges[0], edges[1]),
        (edges[3],),
        (edges[2], edges[4]),
        (),
    )
    incoming = (
        (),
        (edges[0], edges[2]),
        (edges[1],),
        (edges[3], edges[4]),
    )
    instance = Instance(
        name="synthetic-max-delay",
        path=Path("synthetic-max-delay.sch"),
        n_jobs=2,
        n_resources=1,
        durations=(0, 1, 1, 0),
        demands=((0,), (1,), (1,), (0,)),
        capacities=(2,),
        edges=edges,
        outgoing=outgoing,
        incoming=incoming,
    )

    sgs_instance = adapt_instance(instance)
    schedule, _ = decode_priority_list(sgs_instance, (1, 2))

    assert schedule is not None
    assert schedule.start_times[1] == 1
    assert schedule.start_times[2] == 2
    assert validate_schedule(instance, schedule) == []


def test_sgs_beam_decoder_finds_schedule_on_small_instance() -> None:
    instance = parse_sch("benchmarks/data/sm_j10/PSP1.SCH")
    sgs_instance = adapt_instance(instance)
    temporal_lower = longest_feasible_starts(instance)
    priority = seed_priority_lists(sgs_instance, temporal_lower)[0]

    schedule, stats = beam_decode_priority_list(
        sgs_instance,
        priority,
        deadline=time.perf_counter() + 0.2,
    )

    assert schedule is not None
    assert stats.attempts >= 0
    assert validate_schedule(instance, schedule) == []


def test_sgs_solver_reports_obvious_pairwise_infeasibility() -> None:
    instance = parse_sch("benchmarks/data/sm_j10/PSP108.SCH")
    result = solve_sgs(instance, time_limit=0.1, seed=0)

    assert result.status == "infeasible"
    assert result.schedule is None
