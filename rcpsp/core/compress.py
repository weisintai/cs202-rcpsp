from __future__ import annotations

from ..models import Edge, Instance, Schedule
from ..temporal import TemporalInfeasibleError, longest_feasible_starts
from ..validate import build_resource_profile, validate_schedule


def left_shift(instance: Instance, start_times: list[int], extra_edges: list[Edge]) -> list[int]:
    schedule = start_times[:]
    profile = build_resource_profile(instance, schedule)
    extra_incoming: list[list[Edge]] = [[] for _ in range(instance.n_activities)]
    for edge in extra_edges:
        extra_incoming[edge.target].append(edge)

    def ensure_horizon(horizon: int) -> None:
        while len(profile) < horizon:
            profile.append([0] * instance.n_resources)

    for _ in range(instance.n_activities):
        changed = False
        ordered = sorted(range(1, instance.n_activities), key=lambda activity: (schedule[activity], activity))
        for activity in ordered:
            duration = instance.durations[activity]
            current_start = schedule[activity]

            if duration > 0:
                for time_index in range(current_start, current_start + duration):
                    row = profile[time_index]
                    for resource in range(instance.n_resources):
                        row[resource] -= instance.demands[activity][resource]

            earliest = 0
            for edge in instance.incoming[activity]:
                earliest = max(earliest, schedule[edge.source] + edge.lag)
            for edge in extra_incoming[activity]:
                earliest = max(earliest, schedule[edge.source] + edge.lag)

            candidate = earliest
            if duration > 0:
                while candidate < current_start:
                    ensure_horizon(candidate + duration)
                    feasible = True
                    for time_index in range(candidate, candidate + duration):
                        row = profile[time_index]
                        for resource in range(instance.n_resources):
                            if row[resource] + instance.demands[activity][resource] > instance.capacities[resource]:
                                feasible = False
                                candidate = time_index + 1
                                break
                        if not feasible:
                            break
                    if feasible:
                        break
                if candidate >= current_start:
                    candidate = current_start

            if candidate < current_start:
                schedule[activity] = candidate
                changed = True

            new_start = schedule[activity]
            if duration > 0:
                ensure_horizon(new_start + duration)
                for time_index in range(new_start, new_start + duration):
                    row = profile[time_index]
                    for resource in range(instance.n_resources):
                        row[resource] += instance.demands[activity][resource]

        if not changed:
            break

    schedule[instance.source] = 0
    schedule[instance.sink] = max(
        (schedule[edge.source] + edge.lag for edge in instance.incoming[instance.sink]),
        default=0,
    )
    return schedule


def resource_order_edges(instance: Instance, start_times: list[int]) -> list[Edge]:
    edges: list[Edge] = []
    for first in range(1, instance.sink):
        for second in range(first + 1, instance.sink):
            shared = any(
                instance.demands[first][resource] > 0 and instance.demands[second][resource] > 0
                for resource in range(instance.n_resources)
            )
            if not shared:
                continue

            first_end = start_times[first] + instance.durations[first]
            second_end = start_times[second] + instance.durations[second]
            if first_end <= start_times[second]:
                edges.append(Edge(source=first, target=second, lag=instance.durations[first]))
            elif second_end <= start_times[first]:
                edges.append(Edge(source=second, target=first, lag=instance.durations[second]))
    return edges


def compress_valid_schedule(instance: Instance, start_times: list[int]) -> list[int]:
    current = start_times[:]
    resource_edges = resource_order_edges(instance, current)
    if not resource_edges:
        return current

    try:
        compressed = longest_feasible_starts(instance, extra_edges=resource_edges)
    except TemporalInfeasibleError:
        return current

    candidate = Schedule(start_times=tuple(compressed), makespan=compressed[instance.sink])
    if validate_schedule(instance, candidate):
        return current
    return compressed


def normalized_time_loads(instance: Instance, start_times: list[int] | tuple[int, ...]) -> list[float]:
    profile = build_resource_profile(instance, start_times)
    loads: list[float] = []
    for usage in profile:
        load = 0.0
        for resource, amount in enumerate(usage):
            capacity = instance.capacities[resource]
            if capacity == 0:
                continue
            load += amount / capacity
        loads.append(load)
    return loads
