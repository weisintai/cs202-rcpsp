from __future__ import annotations

from pathlib import Path

from rcpsp.core.lag import all_pairs_longest_lags
from rcpsp.cp.propagation import propagate_cp_node, tighten_latest_starts
from rcpsp.models import Edge, Instance


def _chain_instance() -> Instance:
    n_jobs = 2
    n_activities = n_jobs + 2
    edges = (
        Edge(source=0, target=1, lag=0),
        Edge(source=0, target=2, lag=0),
        Edge(source=1, target=2, lag=3),
        Edge(source=1, target=3, lag=5),
        Edge(source=2, target=3, lag=2),
    )
    outgoing = [[] for _ in range(n_activities)]
    incoming = [[] for _ in range(n_activities)]
    for edge in edges:
        outgoing[edge.source].append(edge)
        incoming[edge.target].append(edge)

    return Instance(
        name="chain",
        path=Path("chain.sch"),
        n_jobs=n_jobs,
        n_resources=1,
        durations=(0, 3, 2, 0),
        demands=((0,), (0,), (0,), (0,)),
        capacities=(1,),
        edges=edges,
        outgoing=tuple(tuple(items) for items in outgoing),
        incoming=tuple(tuple(items) for items in incoming),
    )


def test_propagate_cp_node_keeps_lag_dist_with_incumbent() -> None:
    instance = _chain_instance()
    base_lag_dist = all_pairs_longest_lags(instance)

    propagation = propagate_cp_node(
        instance=instance,
        tail=[0, 5, 2, 0],
        pairs=frozenset(),
        incumbent_makespan=10,
        base_lag_dist=base_lag_dist,
    )

    assert propagation.node is not None
    assert propagation.node.lag_dist is not None


def test_propagate_cp_node_detects_cycle_with_incumbent_lag_dist() -> None:
    instance = _chain_instance()
    base_lag_dist = all_pairs_longest_lags(instance)

    propagation = propagate_cp_node(
        instance=instance,
        tail=[0, 5, 2, 0],
        pairs=frozenset({(2, 1)}),
        incumbent_makespan=10,
        base_lag_dist=base_lag_dist,
        new_edges=(Edge(source=2, target=1, lag=2),),
    )

    assert propagation.node is None


def test_tighten_latest_starts_matches_edge_relaxation_with_lag_dist() -> None:
    instance = _chain_instance()
    latest = [0, 8, 8, 10]
    lag_dist = all_pairs_longest_lags(instance)

    via_edges = tighten_latest_starts(instance, (), latest, None)
    via_dist = tighten_latest_starts(instance, (), latest, lag_dist)

    assert via_dist == via_edges
