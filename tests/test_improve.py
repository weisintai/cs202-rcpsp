from __future__ import annotations

from pathlib import Path

from rcpsp.core.metrics import resource_intensity
from rcpsp.heuristic.improve import (
    bottleneck_pair_repair_plans,
    critical_chain_removal_set,
    peak_focused_removal_set,
)
from rcpsp.models import Edge, Instance, Schedule
from rcpsp.temporal import longest_tail_to_sink


def _make_single_resource_instance(
    name: str,
    durations: tuple[int, ...],
    demands: tuple[int, ...],
    capacity: int,
    extra_edges: tuple[tuple[int, int, int], ...] = (),
) -> Instance:
    n_jobs = len(durations)
    n_activities = n_jobs + 2
    full_durations = (0, *durations, 0)
    full_demands = ((0,), *((demand,) for demand in demands), (0,))

    edges: list[Edge] = []
    for activity in range(1, n_jobs + 1):
        edges.append(Edge(source=0, target=activity, lag=0))
        edges.append(Edge(source=activity, target=n_jobs + 1, lag=full_durations[activity]))
    edges.extend(Edge(source, target, lag) for source, target, lag in extra_edges)

    outgoing = [[] for _ in range(n_activities)]
    incoming = [[] for _ in range(n_activities)]
    for edge in edges:
        outgoing[edge.source].append(edge)
        incoming[edge.target].append(edge)

    return Instance(
        name=name,
        path=Path(name),
        n_jobs=n_jobs,
        n_resources=1,
        durations=tuple(full_durations),
        demands=tuple(full_demands),
        capacities=(capacity,),
        edges=tuple(edges),
        outgoing=tuple(tuple(values) for values in outgoing),
        incoming=tuple(tuple(values) for values in incoming),
    )


def test_critical_chain_removal_targets_low_slack_activities() -> None:
    instance = _make_single_resource_instance(
        name="critical-chain-toy",
        durations=(3, 2, 2),
        demands=(1, 2, 3),
        capacity=5,
    )
    schedule = Schedule(start_times=(0, 0, 4, 5, 7), makespan=7)

    removed = critical_chain_removal_set(
        instance=instance,
        schedule=schedule,
        tail=longest_tail_to_sink(instance),
        intensity=resource_intensity(instance),
        size=2,
    )

    assert removed == {2, 3}


def test_peak_focused_removal_targets_high_load_window() -> None:
    instance = _make_single_resource_instance(
        name="peak-toy",
        durations=(3, 3, 2, 1),
        demands=(2, 2, 1, 1),
        capacity=4,
    )
    schedule = Schedule(start_times=(0, 0, 1, 5, 6, 7), makespan=7)

    removed = peak_focused_removal_set(
        instance=instance,
        schedule=schedule,
        tail=longest_tail_to_sink(instance),
        intensity=resource_intensity(instance),
        size=2,
    )

    assert removed == {1, 2}


def test_bottleneck_pair_plans_offer_reinsertion_and_swap() -> None:
    instance = _make_single_resource_instance(
        name="pair-toy",
        durations=(3, 3, 3),
        demands=(2, 2, 1),
        capacity=4,
    )
    schedule = Schedule(start_times=(0, 0, 1, 4, 7), makespan=7)

    plans = bottleneck_pair_repair_plans(
        instance=instance,
        schedule=schedule,
        tail=longest_tail_to_sink(instance),
        intensity=resource_intensity(instance),
        size=3,
    )

    preferred = {plan.preferred_pairs for plan in plans}
    assert () in preferred
    assert ((1, 2),) in preferred
    assert ((2, 1),) in preferred
    assert any({1, 2}.issubset(plan.removed) for plan in plans)
