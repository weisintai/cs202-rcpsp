from __future__ import annotations

from typing import Literal
from weakref import WeakKeyDictionary

from ..core.conflicts import select_branch_conflict
from ..core.lag import (
    all_pairs_longest_lags,
    extend_longest_lags,
    extend_longest_lags_inplace,
    pairwise_infeasibility_reason_from_dist,
)
from ..models import Edge, Instance
from ..temporal import TemporalInfeasibleError
from .state import CpNode, CpNodePropagation, OverloadExplanation

PropagationMode = Literal["fast", "deep"]

_RESOURCE_ACTIVITIES_CACHE: WeakKeyDictionary[Instance, tuple[tuple[int, ...], ...]] = WeakKeyDictionary()

def _resource_activities(
    instance: Instance,
) -> tuple[tuple[int, ...], ...]:
    cached = _RESOURCE_ACTIVITIES_CACHE.get(instance)
    if cached is not None:
        return cached
    computed = tuple(
        tuple(
            activity
            for activity in range(1, instance.sink)
            if instance.durations[activity] > 0 and instance.demands[activity][resource] > 0
        )
        for resource in range(instance.n_resources)
    )
    _RESOURCE_ACTIVITIES_CACHE[instance] = computed
    return computed


def _enqueue(worklist: list[str], pending: set[str], *steps: str) -> None:
    for step in steps:
        if step in pending:
            continue
        worklist.append(step)
        pending.add(step)


def _propagation_overload_node(
    *,
    lower: list[int],
    latest: list[int],
    edges: list[Edge],
    local_pairs: set[tuple[int, int]],
    lag_dist: list[list[float]] | None,
    overload: OverloadExplanation,
    rounds: int,
) -> CpNodePropagation:
    return CpNodePropagation(
        node=CpNode(
            lower=tuple(lower),
            latest=tuple(latest),
            edges=tuple(edges),
            pairs=frozenset(local_pairs),
            lag_dist=lag_dist,
        ),
        overload=overload,
        rounds=rounds,
    )


def _final_propagation_node(
    *,
    instance: Instance,
    lower: list[int],
    latest: list[int] | None,
    edges: list[Edge],
    local_pairs: set[tuple[int, int]],
    lag_dist: list[list[float]] | None,
    rounds: int,
) -> CpNodePropagation:
    branch_conflict = select_branch_conflict(instance, lower, tuple(latest) if latest is not None else None)
    return CpNodePropagation(
        node=CpNode(
            lower=tuple(lower),
            latest=tuple(latest) if latest is not None else None,
            edges=tuple(edges),
            pairs=frozenset(local_pairs),
            lag_dist=lag_dist,
            branch_conflict=branch_conflict,
        ),
        rounds=rounds,
    )


def _propagate_cp_node_fast(
    *,
    instance: Instance,
    edges: list[Edge],
    local_pairs: set[tuple[int, int]],
    lag_dist: list[list[float]] | None,
    latest: list[int] | None,
    release_bounds: list[int],
    incumbent_makespan: int | None,
) -> CpNodePropagation:
    rounds = 0
    lag_dist_checked = False

    while True:
        rounds += 1
        try:
            lower = tighten_earliest_starts(instance, release_bounds, lag_dist)
        except TemporalInfeasibleError:
            return CpNodePropagation(node=None, rounds=rounds)

        if incumbent_makespan is not None and lower[instance.sink] >= incumbent_makespan:
            return CpNodePropagation(node=None, rounds=rounds)

        if lag_dist is not None and not lag_dist_checked:
            if pairwise_infeasibility_reason_from_dist(instance, lag_dist) is not None:
                return CpNodePropagation(node=None, rounds=rounds)
            lag_dist_checked = True

        if latest is None:
            return _final_propagation_node(
                instance=instance,
                lower=lower,
                latest=None,
                edges=edges,
                local_pairs=local_pairs,
                lag_dist=lag_dist,
                rounds=rounds,
            )

        latest = tighten_latest_starts(instance, edges, latest, lag_dist)
        if any(lower[activity] > latest[activity] for activity in range(instance.n_activities)):
            return CpNodePropagation(node=None, rounds=rounds)

        propagated = propagate_compulsory_parts(instance, lower, latest)
        if propagated is None:
            return CpNodePropagation(node=None, rounds=rounds)

        changed, new_lower, new_latest, overload = propagated
        if overload is not None:
            return _propagation_overload_node(
                lower=new_lower,
                latest=new_latest,
                edges=edges,
                local_pairs=local_pairs,
                lag_dist=lag_dist,
                overload=overload,
                rounds=rounds,
            )

        lower = new_lower
        latest = new_latest
        if not changed:
            return _final_propagation_node(
                instance=instance,
                lower=lower,
                latest=latest,
                edges=edges,
                local_pairs=local_pairs,
                lag_dist=lag_dist,
                rounds=rounds,
            )

        release_bounds = lower


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


def tighten_earliest_starts(
    instance: Instance,
    release_times: list[int],
    lag_dist: list[list[float]],
) -> list[int]:
    lower = release_times[:]
    lower[instance.source] = 0
    neg_inf = float("-inf")

    for activity in range(instance.n_activities):
        if lag_dist[activity][activity] > 0:
            raise TemporalInfeasibleError(
                f"{instance.name} contains an inconsistent lag cycle involving activity {activity}"
            )

    updated = lower[:]
    for target in range(instance.n_activities):
        best = lower[target]
        for source in range(instance.n_activities):
            lag = lag_dist[source][target]
            if lag == neg_inf:
                continue
            candidate = lower[source] + int(lag)
            if candidate > best:
                best = candidate
        updated[target] = best
    updated[instance.source] = 0
    return updated


def build_mandatory_profile(
    instance: Instance,
    lower: list[int],
    latest: list[int],
) -> tuple[list[list[int]], list[tuple[list[tuple[int, int, int]], int, tuple[int, ...]]]]:
    horizon = max(
        lower[instance.sink],
        max((max(lower[activity], latest[activity]) + instance.durations[activity] for activity in range(instance.n_activities)), default=0),
    )
    profiles = [[0] * max(0, horizon) for _ in range(instance.n_resources)]
    mandatory_intervals: list[tuple[list[tuple[int, int, int]], int, tuple[int, ...]]] = []
    resource_activity_lists = _resource_activities(instance)

    for resource in range(instance.n_resources):
        mandatory: list[tuple[int, int, int]] = []
        resource_activities = resource_activity_lists[resource]
        deltas = [0] * (horizon + 1)
        for activity in resource_activities:
            duration = instance.durations[activity]
            demand = instance.demands[activity][resource]
            left = latest[activity]
            right = lower[activity] + duration
            if left >= right:
                continue
            start = max(0, left)
            end = min(horizon, right)
            if start >= end:
                continue
            mandatory.append((activity, start, end))
            deltas[start] += demand
            deltas[end] -= demand
        running = 0
        profile = profiles[resource]
        for time_index in range(horizon):
            running += deltas[time_index]
            profile[time_index] = running
        mandatory_intervals.append((mandatory, horizon, resource_activities))

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
    active.sort(key=lambda a: (instance.demands[a][resource], instance.durations[a], a))
    total = sum(instance.demands[a][resource] for a in active)
    i = 0
    while i < len(active):
        if total - instance.demands[active[i]][resource] > instance.capacities[resource]:
            total -= instance.demands[active[i]][resource]
            i += 1
        else:
            break
    conflict = sorted(active[i:])
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

    for resource, (mandatory, horizon, resource_activities) in enumerate(mandatory_intervals):
        if not mandatory:
            continue
        profile = profiles[resource]
        for time_index, usage in enumerate(profile):
            if usage <= instance.capacities[resource]:
                continue
            explanation = minimal_overload_explanation(instance, resource, time_index, mandatory)
            return changed, lower, latest, explanation

        for activity in resource_activities:
            demand = instance.demands[activity][resource]
            duration = instance.durations[activity]
            if lower[activity] >= latest[activity]:
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
    resource_conflict_pairs: frozenset[tuple[int, int]] | None = None,
) -> tuple[tuple[tuple[int, int], ...], OverloadExplanation | None]:
    if instance.n_jobs < 20:
        return (), None

    inferred: list[tuple[int, int]] = []
    pending = set(pairs)

    # Use precomputed conflicting pairs if provided, else fall back to all pairs.
    if resource_conflict_pairs is not None:
        pairs_to_check: tuple[tuple[int, int], ...] | frozenset[tuple[int, int]] = resource_conflict_pairs
    else:
        pairs_to_check = tuple(
            (first, second)
            for first in range(1, instance.sink)
            for second in range(first + 1, instance.sink)
        )

    for first, second in pairs_to_check:
        if (first, second) in pending or (second, first) in pending:
            continue

        forced_pair: tuple[int, int] | None = None

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
    propagation_mode: PropagationMode = "fast",
    base_lag_dist: list[list[float]] | None = None,
    new_edges: tuple[Edge, ...] = (),
    release_times: tuple[int, ...] | list[int] | None = None,
    resource_conflict_pairs: frozenset[tuple[int, int]] | None = None,
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
    else:
        lag_dist = all_pairs_longest_lags(instance, extra_edges=edges)

    latest = improving_latest_starts(instance, tail, incumbent_makespan)
    release_bounds = [0] * instance.n_activities if release_times is None else [max(0, int(value)) for value in release_times]

    if propagation_mode == "fast":
        return _propagate_cp_node_fast(
            instance=instance,
            edges=edges,
            local_pairs=local_pairs,
            lag_dist=lag_dist,
            latest=latest,
            release_bounds=release_bounds,
            incumbent_makespan=incumbent_makespan,
        )

    rounds = 0
    lower: list[int] | None = None
    worklist = ["temporal", "pairwise"]
    pending = {"temporal", "pairwise"}
    if latest is not None:
        _enqueue(worklist, pending, "latest", "timetable")
        if propagation_mode == "deep":
            _enqueue(worklist, pending, "pairs")

    while worklist:
        rounds += 1
        step = worklist.pop(0)
        pending.remove(step)

        if step == "temporal":
            try:
                updated_lower = tighten_earliest_starts(instance, release_bounds, lag_dist)
            except TemporalInfeasibleError:
                return CpNodePropagation(node=None, rounds=rounds)

            lower_changed = lower != updated_lower
            lower = updated_lower

            if incumbent_makespan is not None and lower[instance.sink] >= incumbent_makespan:
                return CpNodePropagation(node=None, rounds=rounds)

            if latest is not None and any(lower[activity] > latest[activity] for activity in range(instance.n_activities)):
                return CpNodePropagation(node=None, rounds=rounds)

            if lower_changed and latest is not None:
                _enqueue(worklist, pending, "latest", "timetable")
                if propagation_mode == "deep":
                    _enqueue(worklist, pending, "pairs")
            continue

        if step == "pairwise":
            if lag_dist is not None and pairwise_infeasibility_reason_from_dist(instance, lag_dist) is not None:
                return CpNodePropagation(node=None, rounds=rounds)
            continue

        if latest is None or lower is None:
            continue

        if step == "latest":
            updated_latest = tighten_latest_starts(instance, edges, latest, lag_dist)
            latest_changed = latest != updated_latest
            latest = updated_latest
            if any(lower[activity] > latest[activity] for activity in range(instance.n_activities)):
                return CpNodePropagation(node=None, rounds=rounds)
            if latest_changed:
                _enqueue(worklist, pending, "timetable")
                if propagation_mode == "deep":
                    _enqueue(worklist, pending, "pairs")
            continue

        if step == "timetable":
            propagated = propagate_compulsory_parts(instance, lower[:], latest[:])
            if propagated is None:
                return CpNodePropagation(node=None, rounds=rounds)

            changed, new_lower, new_latest, overload = propagated
            if overload is not None:
                return _propagation_overload_node(
                    lower=new_lower,
                    latest=new_latest,
                    edges=edges,
                    local_pairs=local_pairs,
                    lag_dist=lag_dist,
                    overload=overload,
                    rounds=rounds,
                )

            if changed:
                lower = new_lower
                latest = new_latest
                release_bounds = lower[:]
                if any(lower[activity] > latest[activity] for activity in range(instance.n_activities)):
                    return CpNodePropagation(node=None, rounds=rounds)
                _enqueue(worklist, pending, "temporal", "pairwise", "latest")
                if propagation_mode == "deep":
                    _enqueue(worklist, pending, "pairs")
            continue

        if step == "pairs":
            if propagation_mode != "deep":
                continue

            inferred_pairs, pair_overload = forced_pair_order_propagation(
                instance,
                lower,
                latest,
                local_pairs,
                resource_conflict_pairs=resource_conflict_pairs,
            )
            if pair_overload is not None:
                return _propagation_overload_node(
                    lower=lower,
                    latest=latest,
                    edges=edges,
                    local_pairs=local_pairs,
                    lag_dist=lag_dist,
                    overload=pair_overload,
                    rounds=rounds,
                )

            if inferred_pairs:
                if lag_dist is not None and lag_dist is base_lag_dist:
                    lag_dist = [row[:] for row in lag_dist]
                for source, target in inferred_pairs:
                    local_pairs.add((source, target))
                    edge = Edge(source=source, target=target, lag=instance.durations[source])
                    edges.append(edge)
                    if lag_dist is not None:
                        extend_longest_lags_inplace(lag_dist, edge)
                _enqueue(worklist, pending, "temporal", "pairwise", "latest", "timetable", "pairs")
            continue

    if lower is None:
        lower = release_bounds[:]
    return _final_propagation_node(
        instance=instance,
        lower=lower,
        latest=latest,
        edges=edges,
        local_pairs=local_pairs,
        lag_dist=lag_dist,
        rounds=rounds,
    )
