from __future__ import annotations

from pathlib import Path

from rcpsp.cp_full.propagation import propagate_cp_node
from rcpsp.models import Edge, Instance


def _pair_conflict_instance() -> Instance:
    n_jobs = 20
    n_activities = n_jobs + 2
    sink = n_jobs + 1
    durations = [0] + [0] * n_jobs + [0]
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
            Edge(source=activity, target=sink, lag=0),
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


def test_cp_full_fast_mode_skips_dynamic_pair_inference() -> None:
    instance = _pair_conflict_instance()

    propagation = propagate_cp_node(
        instance=instance,
        tail=[0, 5, 0] + [0] * (instance.n_activities - 3),
        pairs=frozenset(),
        incumbent_makespan=6,
        propagation_mode="fast",
        resource_conflict_pairs=frozenset({(1, 2)}),
    )

    assert propagation.node is not None
    assert (1, 2) not in propagation.node.pairs


def test_cp_full_deep_mode_runs_dynamic_pair_inference() -> None:
    instance = _pair_conflict_instance()

    propagation = propagate_cp_node(
        instance=instance,
        tail=[0, 5, 0] + [0] * (instance.n_activities - 3),
        pairs=frozenset(),
        incumbent_makespan=6,
        propagation_mode="deep",
        resource_conflict_pairs=frozenset({(1, 2)}),
    )

    assert propagation.node is not None
    assert (1, 2) in propagation.node.pairs
