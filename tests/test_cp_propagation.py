from __future__ import annotations

from pathlib import Path

from rcpsp.core.lag import all_pairs_longest_lags
from rcpsp.cp.propagation import (
    forced_pair_order_propagation,
    propagate_cp_node,
    tighten_earliest_starts,
    tighten_latest_starts,
)
from rcpsp.models import Edge, Instance
from rcpsp.temporal import TemporalInfeasibleError, longest_feasible_starts


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


def _pair_conflict_instance() -> Instance:
    n_jobs = 20
    n_activities = n_jobs + 2
    sink = n_jobs + 1
    durations = [0] + [1] * n_jobs + [0]
    durations[1] = 3
    durations[2] = 3
    demands = [(0,)] + [(0,)] * n_jobs + [(0,)]
    demands[1] = (1,)
    demands[2] = (1,)
    edges: list[Edge] = []
    outgoing = [[] for _ in range(n_activities)]
    incoming = [[] for _ in range(n_activities)]

    for activity in range(1, sink):
        for edge in (
            Edge(source=0, target=activity, lag=0),
            Edge(source=activity, target=sink, lag=durations[activity]),
        ):
            edges.append(edge)
            outgoing[edge.source].append(edge)
            incoming[edge.target].append(edge)

    return Instance(
        name="pair-conflict",
        path=Path("pair-conflict.sch"),
        n_jobs=n_jobs,
        n_resources=1,
        durations=tuple(durations),
        demands=tuple(demands),
        capacities=(1,),
        edges=tuple(edges),
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
    assert propagation.rounds >= 1


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
    assert propagation.rounds >= 1


def test_tighten_latest_starts_matches_edge_relaxation_with_lag_dist() -> None:
    instance = _chain_instance()
    latest = [0, 8, 8, 10]
    lag_dist = all_pairs_longest_lags(instance)

    via_edges = tighten_latest_starts(instance, (), latest, None)
    via_dist = tighten_latest_starts(instance, (), latest, lag_dist)

    assert via_dist == via_edges


def test_tighten_earliest_starts_matches_temporal_closure_with_lag_dist() -> None:
    instance = _chain_instance()
    release_times = [0, 1, 0, 4]
    lag_dist = all_pairs_longest_lags(instance)

    via_edges = longest_feasible_starts(instance, release_times=release_times)
    via_dist = tighten_earliest_starts(instance, release_times, lag_dist)

    assert via_dist == via_edges


def test_tighten_earliest_starts_detects_positive_cycle_from_lag_dist() -> None:
    instance = _chain_instance()
    lag_dist = all_pairs_longest_lags(instance, extra_edges=(Edge(source=2, target=1, lag=2),))

    try:
        tighten_earliest_starts(instance, [0] * instance.n_activities, lag_dist)
    except TemporalInfeasibleError:
        pass
    else:
        raise AssertionError("expected a temporal cycle to be detected from lag_dist")


def test_forced_pair_order_propagation_infers_order() -> None:
    instance = _pair_conflict_instance()
    lower = [0] * instance.n_activities
    latest = [0] * instance.n_activities
    latest[2] = 5

    inferred, overload = forced_pair_order_propagation(
        instance,
        lower,
        latest,
        set(),
        resource_conflict_pairs=frozenset({(1, 2)}),
    )

    assert inferred == ((1, 2),)
    assert overload is None


def test_forced_pair_order_propagation_reports_pair_overload() -> None:
    instance = _pair_conflict_instance()
    lower = [0] * instance.n_activities
    latest = [0] * instance.n_activities

    inferred, overload = forced_pair_order_propagation(
        instance,
        lower,
        latest,
        set(),
        resource_conflict_pairs=frozenset({(1, 2)}),
    )

    assert inferred == ()
    assert overload is not None
    assert overload.kind == "pair"
    assert overload.activities == (1, 2)


def test_propagate_cp_node_caches_ranked_branch_conflict() -> None:
    instance = _pair_conflict_instance()

    propagation = propagate_cp_node(
        instance=instance,
        tail=[0] * instance.n_activities,
        pairs=frozenset(),
        incumbent_makespan=None,
    )

    assert propagation.node is not None
    assert propagation.node.branch_conflict is not None
    _, resource, activities, overload = propagation.node.branch_conflict
    assert resource == 0
    assert activities == (1, 2)
    assert overload == (1,)
