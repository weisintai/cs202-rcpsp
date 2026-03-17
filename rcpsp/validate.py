from __future__ import annotations

from .models import Instance, Schedule


def build_resource_profile(instance: Instance, start_times: list[int] | tuple[int, ...]) -> list[list[int]]:
    horizon = 0
    for activity, start in enumerate(start_times):
        horizon = max(horizon, start + instance.durations[activity])
    profile = [[0] * instance.n_resources for _ in range(horizon)]
    for activity, start in enumerate(start_times):
        duration = instance.durations[activity]
        if duration == 0:
            continue
        demand = instance.demands[activity]
        for t in range(start, start + duration):
            row = profile[t]
            for resource in range(instance.n_resources):
                row[resource] += demand[resource]
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
