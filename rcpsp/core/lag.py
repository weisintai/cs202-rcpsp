from __future__ import annotations

from ..models import Edge, Instance


def all_pairs_longest_lags(instance: Instance, extra_edges: list[Edge] | tuple[Edge, ...] = ()) -> list[list[float]]:
    n = instance.n_activities
    neg_inf = float("-inf")
    dist = [[neg_inf] * n for _ in range(n)]
    for activity in range(n):
        dist[activity][activity] = 0
    for edge in tuple(instance.edges) + tuple(extra_edges):
        dist[edge.source][edge.target] = max(dist[edge.source][edge.target], edge.lag)
    for via in range(n):
        for source in range(n):
            if dist[source][via] == neg_inf:
                continue
            for target in range(n):
                if dist[via][target] == neg_inf:
                    continue
                candidate = dist[source][via] + dist[via][target]
                if candidate > dist[source][target]:
                    dist[source][target] = candidate
    return dist


def extend_longest_lags(dist: list[list[float]], edge: Edge) -> list[list[float]]:
    if dist[edge.source][edge.target] >= edge.lag:
        return dist

    neg_inf = float("-inf")
    n = len(dist)
    updated = [row[:] for row in dist]
    updated[edge.source][edge.target] = edge.lag

    for source in range(n):
        left = dist[source][edge.source]
        if left == neg_inf:
            continue
        for target in range(n):
            right = dist[edge.target][target]
            if right == neg_inf:
                continue
            candidate = left + edge.lag + right
            if candidate > updated[source][target]:
                updated[source][target] = candidate
    return updated


def pairwise_infeasibility_reason_from_dist(instance: Instance, dist: list[list[float]]) -> str | None:
    for first in range(1, instance.sink):
        for second in range(first + 1, instance.sink):
            lower = dist[first][second]
            upper = float("inf") if dist[second][first] == float("-inf") else -dist[second][first]
            mandatory_overlap = lower > -instance.durations[second] and upper < instance.durations[first]
            if not mandatory_overlap:
                continue
            for resource in range(instance.n_resources):
                demand = instance.demands[first][resource] + instance.demands[second][resource]
                if demand > instance.capacities[resource]:
                    return (
                        f"activities {first} and {second} must overlap and need {demand} units "
                        f"of resource {resource}, exceeding capacity {instance.capacities[resource]}"
                    )
    return None


def _upper_bound(dist: list[list[float]], source: int, target: int) -> float:
    reverse = dist[target][source]
    if reverse == float("-inf"):
        return float("inf")
    return -reverse


def forced_resource_order_edges_from_dist(
    instance: Instance,
    dist: list[list[float]],
) -> tuple[list[Edge], list[list[float]]]:
    inferred: list[Edge] = []
    updated = dist

    while True:
        added = False
        for first in range(1, instance.sink):
            for second in range(first + 1, instance.sink):
                if not any(
                    instance.demands[first][resource] + instance.demands[second][resource] > instance.capacities[resource]
                    for resource in range(instance.n_resources)
                ):
                    continue

                if updated[first][second] >= instance.durations[first] or updated[second][first] >= instance.durations[second]:
                    continue

                first_before_second_possible = _upper_bound(updated, first, second) >= instance.durations[first]
                second_before_first_possible = updated[first][second] <= -instance.durations[second]

                if first_before_second_possible == second_before_first_possible:
                    continue

                if first_before_second_possible:
                    edge = Edge(source=first, target=second, lag=instance.durations[first])
                else:
                    edge = Edge(source=second, target=first, lag=instance.durations[second])

                if updated[edge.source][edge.target] >= edge.lag:
                    continue
                inferred.append(edge)
                updated = extend_longest_lags(updated, edge)
                added = True
        if not added:
            break

    return inferred, updated


def pairwise_infeasibility_reason(
    instance: Instance,
    extra_edges: list[Edge] | tuple[Edge, ...] = (),
) -> str | None:
    for activity in range(instance.n_activities):
        for resource in range(instance.n_resources):
            if instance.demands[activity][resource] > instance.capacities[resource]:
                return (
                    f"activity {activity} exceeds capacity of resource {resource}: "
                    f"{instance.demands[activity][resource]} > {instance.capacities[resource]}"
                )

    dist = all_pairs_longest_lags(instance, extra_edges)
    return pairwise_infeasibility_reason_from_dist(instance, dist)
