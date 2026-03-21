from pathlib import Path

from rcpsp.core.lag import all_pairs_longest_lags, forced_resource_order_edges_from_dist
from rcpsp.models import Edge, Instance


def _make_instance(
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


def test_forced_resource_order_edges_infers_unique_non_overlap_direction() -> None:
    instance = _make_instance(
        name="forced-order",
        durations=(3, 2),
        demands=(1, 1),
        capacity=1,
        extra_edges=((1, 2, 0),),
    )

    dist = all_pairs_longest_lags(instance)
    edges, updated = forced_resource_order_edges_from_dist(instance, dist)

    assert [(edge.source, edge.target, edge.lag) for edge in edges] == [(1, 2, 3)]
    assert updated[1][2] >= 3


def test_forced_resource_order_edges_does_not_force_when_both_orders_still_possible() -> None:
    instance = _make_instance(
        name="optional-order",
        durations=(3, 2),
        demands=(1, 1),
        capacity=1,
    )

    dist = all_pairs_longest_lags(instance)
    edges, _ = forced_resource_order_edges_from_dist(instance, dist)

    assert edges == []
