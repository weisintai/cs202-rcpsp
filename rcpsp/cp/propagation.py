from __future__ import annotations

from ..core.lag import (
    all_pairs_longest_lags,
    extend_longest_lags,
    pairwise_infeasibility_reason_from_dist,
)
from ..models import Edge, Instance
from ..temporal import TemporalInfeasibleError, longest_feasible_starts
from .state import CpNode, CpNodePropagation, OverloadExplanation


def tighten_latest_starts(
    instance: Instance,
    extra_edges: tuple[Edge, ...] | list[Edge],
    latest: list[int],
    lag_dist: list[list[float]] | None = None,
) -> list[int]:
    if lag_dist is not None:
        upper = latest[:]
        base = latest[:]
        neg_inf = float("-inf")
        upper[instance.source] = 0
        for source in range(instance.n_activities):
            best = base[source]
            for target in range(instance.n_activities):
                lag = lag_dist[source][target]
                if lag == neg_inf:
                    continue
                candidate = base[target] - int(lag)
                if candidate < best:
                    best = candidate
            upper[source] = best
        upper[instance.source] = 0
        return upper

    upper = latest[:]
    upper[instance.source] = 0
    all_edges = tuple(instance.edges) + tuple(extra_edges)

    for _ in range(instance.n_activities - 1):
        updated = False
        for edge in all_edges:
            candidate = upper[edge.target] - edge.lag
            if candidate < upper[edge.source]:
                upper[edge.source] = candidate
                updated = True
        upper[instance.source] = 0
        if not updated:
            return upper

    upper[instance.source] = 0
    return upper


def build_mandatory_profile(
    instance: Instance,
    lower: list[int],
    latest: list[int],
) -> tuple[list[list[int]], list[tuple[list[tuple[int, int, int]], int]]]:
    horizon = max(
        lower[instance.sink],
        max((max(lower[activity], latest[activity]) + instance.durations[activity] for activity in range(instance.n_activities)), default=0),
    )
    profiles = [[0] * max(0, horizon) for _ in range(instance.n_resources)]
    mandatory_intervals: list[tuple[list[tuple[int, int, int]], int]] = []

    for resource in range(instance.n_resources):
        mandatory: list[tuple[int, int, int]] = []
        for activity in range(1, instance.sink):
            duration = instance.durations[activity]
            demand = instance.demands[activity][resource]
            if duration <= 0 or demand <= 0:
                continue
            left = latest[activity]
            right = lower[activity] + duration
            if left >= right:
                continue
            mandatory.append((activity, left, right))
            for time_index in range(max(0, left), min(horizon, right)):
                profiles[resource][time_index] += demand

        mandatory_intervals.append((mandatory, horizon))

    return profiles, mandatory_intervals


def minimal_overload_explanation(
    instance: Instance,
    resource: int,
    time_index: int,
    mandatory: list[tuple[int, int, int]],
) -> OverloadExplanation:
    active = [
        activity
        for activity, left, right in mandatory
        if left <= time_index < right
    ]
    total = sum(instance.demands[activity][resource] for activity in active)
    conflict = active[:]
    while conflict:
        smallest = min(
            conflict,
            key=lambda activity: (
                instance.demands[activity][resource],
                instance.durations[activity],
                activity,
            ),
        )
        if total - instance.demands[smallest][resource] > instance.capacities[resource]:
            total -= instance.demands[smallest][resource]
            conflict.remove(smallest)
        else:
            break
    conflict.sort()
    return OverloadExplanation(
        kind="point",
        resource=resource,
        window_start=time_index,
        window_end=time_index + 1,
        activities=tuple(conflict),
        required=total,
        limit=instance.capacities[resource],
    )


def minimum_overlap_in_window(
    est: int,
    lst: int,
    duration: int,
    window_start: int,
    window_end: int,
) -> int:
    before = max(0, window_start - est)
    after = max(0, lst + duration - window_end)
    return max(0, duration - before - after)

def propagate_compulsory_parts(
    instance: Instance,
    lower: list[int],
    latest: list[int],
) -> tuple[bool, list[int], list[int], OverloadExplanation | None] | None:
    changed = False
    profiles, mandatory_intervals = build_mandatory_profile(instance, lower, latest)

    for resource, (mandatory, horizon) in enumerate(mandatory_intervals):
        profile = profiles[resource]
        for time_index, usage in enumerate(profile):
            if usage <= instance.capacities[resource]:
                continue
            explanation = minimal_overload_explanation(instance, resource, time_index, mandatory)
            return changed, lower, latest, explanation

        for activity in range(1, instance.sink):
            demand = instance.demands[activity][resource]
            duration = instance.durations[activity]
            if demand <= 0 or duration <= 0:
                continue

            own_left = latest[activity]
            own_right = lower[activity] + duration

            new_lower = lower[activity]
            while new_lower <= latest[activity]:
                moved = False
                for time_index in range(new_lower, min(horizon, new_lower + duration)):
                    load = profile[time_index]
                    if own_left < own_right and own_left <= time_index < own_right:
                        load -= demand
                    if load + demand > instance.capacities[resource]:
                        new_lower = time_index + 1
                        moved = True
                        break
                if not moved:
                    break

            if new_lower > latest[activity]:
                return None
            if new_lower > lower[activity]:
                lower[activity] = new_lower
                changed = True

            own_left = latest[activity]
            own_right = lower[activity] + duration
            new_latest = latest[activity]
            while new_latest >= lower[activity]:
                moved = False
                for time_index in range(new_latest, min(horizon, new_latest + duration)):
                    load = profile[time_index]
                    if own_left < own_right and own_left <= time_index < own_right:
                        load -= demand
                    if load + demand > instance.capacities[resource]:
                        new_latest = time_index - duration
                        moved = True
                        break
                if not moved:
                    break

            if new_latest < lower[activity]:
                return None
            if new_latest < latest[activity]:
                latest[activity] = new_latest
                changed = True

    return changed, lower, latest, None


def forced_pair_order_propagation(
    instance: Instance,
    lower: list[int],
    latest: list[int],
    pairs: set[tuple[int, int]],
) -> tuple[tuple[tuple[int, int], ...], OverloadExplanation | None]:
    if instance.n_jobs < 20:
        return (), None

    inferred: list[tuple[int, int]] = []
    pending = set(pairs)

    for first in range(1, instance.sink):
        for second in range(first + 1, instance.sink):
            if (first, second) in pending or (second, first) in pending:
                continue

            forced_pair: tuple[int, int] | None = None
            blocking_resource: int | None = None

            for resource in range(instance.n_resources):
                combined_demand = instance.demands[first][resource] + instance.demands[second][resource]
                if combined_demand <= instance.capacities[resource]:
                    continue

                first_before_second = lower[first] + instance.durations[first] <= latest[second]
                second_before_first = lower[second] + instance.durations[second] <= latest[first]

                if not first_before_second and not second_before_first:
                    window_start = max(lower[first], lower[second])
                    window_end = min(
                        latest[first] + instance.durations[first],
                        latest[second] + instance.durations[second],
                    )
                    return (), OverloadExplanation(
                        kind="pair",
                        resource=resource,
                        window_start=window_start,
                        window_end=max(window_start + 1, window_end),
                        activities=(first, second),
                        required=combined_demand,
                        limit=instance.capacities[resource],
                    )

                if first_before_second == second_before_first:
                    continue

                candidate = (first, second) if first_before_second else (second, first)
                if forced_pair is not None and forced_pair != candidate:
                    window_start = max(lower[first], lower[second])
                    window_end = min(
                        latest[first] + instance.durations[first],
                        latest[second] + instance.durations[second],
                    )
                    resource = blocking_resource if blocking_resource is not None else resource
                    return (), OverloadExplanation(
                        kind="pair",
                        resource=resource,
                        window_start=window_start,
                        window_end=max(window_start + 1, window_end),
                        activities=(first, second),
                        required=combined_demand,
                        limit=instance.capacities[resource],
                    )
                forced_pair = candidate
                blocking_resource = resource

            if forced_pair is not None and forced_pair not in pending:
                pending.add(forced_pair)
                inferred.append(forced_pair)

    return tuple(inferred), None


def improving_latest_starts(
    instance: Instance,
    tail: list[int],
    incumbent_makespan: int | None,
) -> list[int] | None:
    if incumbent_makespan is None:
        return None
    latest = [incumbent_makespan - 1 - tail[activity] for activity in range(instance.n_activities)]
    latest[instance.source] = 0
    return latest


def propagate_cp_node(
    instance: Instance,
    tail: list[int],
    pairs: frozenset[tuple[int, int]],
    incumbent_makespan: int | None,
    base_lag_dist: list[list[float]] | None = None,
    new_edges: tuple[Edge, ...] = (),
    release_times: tuple[int, ...] | list[int] | None = None,
) -> CpNodePropagation:
    local_pairs = set(pairs)
    if new_edges:
        for edge in new_edges:
            local_pairs.add((edge.source, edge.target))
    edges = [
        Edge(source=source, target=target, lag=instance.durations[source])
        for source, target in sorted(local_pairs)
    ]

    lag_dist = base_lag_dist
    if lag_dist is not None:
        updated = lag_dist
        for edge in new_edges:
            updated = extend_longest_lags(updated, edge)
        lag_dist = updated
    elif not new_edges:
        lag_dist = all_pairs_longest_lags(instance, extra_edges=edges)
    else:
        lag_dist = all_pairs_longest_lags(instance, extra_edges=edges)

    latest = improving_latest_starts(instance, tail, incumbent_makespan)
    release_bounds = [0] * instance.n_activities if release_times is None else [max(0, int(value)) for value in release_times]

    while True:
        try:
            lower = longest_feasible_starts(instance, release_times=release_bounds, extra_edges=edges)
        except TemporalInfeasibleError:
            return CpNodePropagation(node=None)

        if incumbent_makespan is not None and lower[instance.sink] >= incumbent_makespan:
            return CpNodePropagation(node=None)

        if lag_dist is not None:
            if pairwise_infeasibility_reason_from_dist(instance, lag_dist) is not None:
                return CpNodePropagation(node=None)

        if latest is None:
            break

        latest = tighten_latest_starts(instance, edges, latest, lag_dist)
        if any(lower[activity] > latest[activity] for activity in range(instance.n_activities)):
            return CpNodePropagation(node=None)

        propagated = propagate_compulsory_parts(instance, lower[:], latest[:])
        if propagated is None:
            return CpNodePropagation(node=None)

        changed, new_lower, new_latest, overload = propagated
        if overload is not None:
            return CpNodePropagation(
                node=CpNode(
                    lower=tuple(new_lower),
                    latest=tuple(new_latest),
                    edges=tuple(edges),
                    pairs=frozenset(local_pairs),
                    lag_dist=lag_dist,
                ),
                overload=overload,
            )
        lower = new_lower
        latest = new_latest

        inferred_pairs, pair_overload = forced_pair_order_propagation(instance, lower, latest, local_pairs)
        if pair_overload is not None:
            return CpNodePropagation(
                node=CpNode(
                    lower=tuple(lower),
                    latest=tuple(latest),
                    edges=tuple(edges),
                    pairs=frozenset(local_pairs),
                    lag_dist=lag_dist,
                ),
                overload=pair_overload,
            )

        if inferred_pairs:
            for source, target in inferred_pairs:
                local_pairs.add((source, target))
                edge = Edge(source=source, target=target, lag=instance.durations[source])
                edges.append(edge)
                if lag_dist is not None:
                    lag_dist = extend_longest_lags(lag_dist, edge)
            release_bounds = lower
            continue

        if not changed:
            break

        release_bounds = lower

    return CpNodePropagation(
        node=CpNode(
            lower=tuple(lower),
            latest=tuple(latest) if latest is not None else None,
            edges=tuple(edges),
            pairs=frozenset(local_pairs),
            lag_dist=lag_dist,
        )
    )
