from __future__ import annotations

from collections import defaultdict

from ..core.lag import all_pairs_longest_lags
from ..models import Instance
from .graph import stable_topological_order
from .models import Activity, LagArc, MaxLagArc, SgsInstance


def adapt_instance(instance: Instance) -> SgsInstance:
    min_lags: dict[tuple[int, int], int] = {}
    max_lags: dict[tuple[int, int], int] = {}

    for edge in instance.edges:
        if edge.lag >= 0:
            key = (edge.source, edge.target)
            min_lags[key] = max(min_lags.get(key, edge.lag), edge.lag)
            continue

        key = (edge.target, edge.source)
        upper_bound = -edge.lag
        current = max_lags.get(key)
        if current is None or upper_bound < current:
            max_lags[key] = upper_bound

    min_pred: dict[int, list[LagArc]] = defaultdict(list)
    min_succ: dict[int, list[LagArc]] = defaultdict(list)
    max_pred: dict[int, list[MaxLagArc]] = defaultdict(list)
    max_succ: dict[int, list[MaxLagArc]] = defaultdict(list)

    for (source, target), lag in min_lags.items():
        arc = LagArc(activity=target, lag=lag)
        min_succ[source].append(arc)
        min_pred[target].append(LagArc(activity=source, lag=lag))

    for (source, target), lag in max_lags.items():
        arc = MaxLagArc(activity=target, lag=lag)
        max_succ[source].append(arc)
        max_pred[target].append(MaxLagArc(activity=source, lag=lag))

    activities: list[Activity] = []
    for activity in range(instance.n_activities):
        activities.append(
            Activity(
                id=activity,
                duration=instance.durations[activity],
                demands=instance.demands[activity],
                min_predecessors=tuple(sorted(min_pred[activity], key=lambda arc: arc.activity)),
                min_successors=tuple(sorted(min_succ[activity], key=lambda arc: arc.activity)),
                max_predecessors=tuple(sorted(max_pred[activity], key=lambda arc: arc.activity)),
                max_successors=tuple(sorted(max_succ[activity], key=lambda arc: arc.activity)),
            )
        )

    topo_order = stable_topological_order(
        n_activities=instance.n_activities,
        source=instance.source,
        sink=instance.sink,
        edges=sorted(min_lags),
    )
    internal_activities = tuple(activity for activity in topo_order if activity not in (instance.source, instance.sink))
    lag_dist = tuple(tuple(row) for row in all_pairs_longest_lags(instance))

    return SgsInstance(
        base_instance=instance,
        activities=tuple(activities),
        capacities=instance.capacities,
        topo_order=topo_order,
        internal_activities=internal_activities,
        lag_dist=lag_dist,
    )
