from __future__ import annotations

from pathlib import Path

from rcpsp.core.compress import (
    compress_valid_schedule,
    compress_valid_schedule_relaxed,
    compression_order_edges,
)
from rcpsp.models import Edge, Instance


def _make_single_resource_instance(
    name: str,
    durations: tuple[int, ...],
    demands: tuple[int, ...],
    capacity: int,
) -> Instance:
    n_jobs = len(durations)
    n_activities = n_jobs + 2
    full_durations = (0, *durations, 0)
    full_demands = ((0,), *((demand,) for demand in demands), (0,))

    edges: list[Edge] = []
    for activity in range(1, n_jobs + 1):
        edges.append(Edge(source=0, target=activity, lag=0))
        edges.append(Edge(source=activity, target=n_jobs + 1, lag=full_durations[activity]))

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


def test_compression_order_edges_ignore_pairs_that_can_overlap_within_capacity() -> None:
    instance = _make_single_resource_instance(
        name="compress-overlap-ok",
        durations=(3, 2),
        demands=(1, 1),
        capacity=2,
    )

    assert compression_order_edges(instance, [0, 0, 3, 5]) == []


def test_compress_valid_schedule_drops_unnecessary_serialization() -> None:
    instance = _make_single_resource_instance(
        name="compress-serialization",
        durations=(3, 2),
        demands=(1, 1),
        capacity=2,
    )

    assert compress_valid_schedule(instance, [0, 0, 3, 5]) == [0, 0, 3, 5]
    assert compress_valid_schedule_relaxed(instance, [0, 0, 3, 5]) == [0, 0, 0, 3]


def test_compress_valid_schedule_preserves_required_disjunctive_order() -> None:
    instance = _make_single_resource_instance(
        name="compress-disjunctive",
        durations=(3, 2),
        demands=(1, 1),
        capacity=1,
    )

    assert compress_valid_schedule(instance, [0, 0, 3, 5]) == [0, 0, 3, 5]
