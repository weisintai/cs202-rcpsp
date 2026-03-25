from __future__ import annotations

from weakref import WeakKeyDictionary

from .models import Instance, Schedule

_NONZERO_RESOURCE_DEMANDS_CACHE: WeakKeyDictionary[
    Instance, tuple[tuple[tuple[int, int], ...], ...]
] = WeakKeyDictionary()


def _nonzero_resource_demands(
    instance: Instance,
) -> tuple[tuple[tuple[int, int], ...], ...]:
    cached = _NONZERO_RESOURCE_DEMANDS_CACHE.get(instance)
    if cached is not None:
        return cached
    computed = tuple(
        tuple(
            (resource, amount)
            for resource, amount in enumerate(instance.demands[activity])
            if amount != 0
        )
        for activity in range(instance.n_activities)
    )
    _NONZERO_RESOURCE_DEMANDS_CACHE[instance] = computed
    return computed


def build_resource_profile(instance: Instance, start_times: list[int] | tuple[int, ...]) -> list[list[int]]:
    horizon = 0
    for activity, start in enumerate(start_times):
        horizon = max(horizon, start + instance.durations[activity])
    profile = [[0] * instance.n_resources for _ in range(horizon)]
    deltas = [[0] * instance.n_resources for _ in range(horizon + 1)]
    nonzero_demands = _nonzero_resource_demands(instance)
    for activity, start in enumerate(start_times):
        duration = instance.durations[activity]
        if duration == 0:
            continue
        end = start + duration
        start_row = deltas[start]
        end_row = deltas[end]
        for resource, amount in nonzero_demands[activity]:
            start_row[resource] += amount
            end_row[resource] -= amount
    running = [0] * instance.n_resources
    for time_index in range(horizon):
        delta_row = deltas[time_index]
        row = profile[time_index]
        for resource in range(instance.n_resources):
            running[resource] += delta_row[resource]
            row[resource] = running[resource]
    return profile


def validate_schedule(instance: Instance, schedule: Schedule) -> list[str]:
    errors: list[str] = []
    starts = schedule.start_times
    if len(starts) != instance.n_activities:
        errors.append("start vector length does not match the instance size")
        return errors
    if starts[instance.source] != 0:
        errors.append(f"source activity must start at 0, found {starts[instance.source]}")
    for edge in instance.edges:
        lhs = starts[edge.target]
        rhs = starts[edge.source] + edge.lag
        if lhs < rhs:
            errors.append(
                f"lag violation on {edge.source}->{edge.target}: {lhs} < {rhs}"
            )
    profile = build_resource_profile(instance, starts)
    for t, usage in enumerate(profile):
        for resource, amount in enumerate(usage):
            if amount > instance.capacities[resource]:
                errors.append(
                    f"resource violation at time {t} on resource {resource}: {amount} > {instance.capacities[resource]}"
                )
    expected_makespan = starts[instance.sink]
    if schedule.makespan != expected_makespan:
        errors.append(
            f"makespan mismatch: schedule says {schedule.makespan}, sink starts at {expected_makespan}"
        )
    return errors
