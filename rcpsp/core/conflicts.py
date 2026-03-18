from __future__ import annotations

from ..models import Instance
from ..validate import build_resource_profile


def first_conflict(instance: Instance, start_times: list[int]) -> tuple[int, list[int], list[int]] | None:
    profile = build_resource_profile(instance, start_times)
    for time_index, usage in enumerate(profile):
        overload = [max(0, usage[resource] - instance.capacities[resource]) for resource in range(instance.n_resources)]
        if any(amount > 0 for amount in overload):
            active = [
                activity
                for activity in range(1, instance.sink)
                if start_times[activity] <= time_index < start_times[activity] + instance.durations[activity]
            ]
            return time_index, overload, active
    return None


def shared_resource_overload(
    instance: Instance,
    selected: int,
    other: int,
    overload: list[int],
) -> bool:
    return any(
        overload[resource] > 0
        and instance.demands[selected][resource] > 0
        and instance.demands[other][resource] > 0
        for resource in range(instance.n_resources)
    )


def minimal_conflict_set(
    instance: Instance,
    start_times: list[int],
) -> tuple[int, int, list[int], list[int]] | None:
    profile = build_resource_profile(instance, start_times)
    for time_index, usage in enumerate(profile):
        overloaded = [resource for resource in range(instance.n_resources) if usage[resource] > instance.capacities[resource]]
        if not overloaded:
            continue
        resource = max(overloaded, key=lambda idx: usage[idx] - instance.capacities[idx])
        active = [
            activity
            for activity in range(1, instance.sink)
            if start_times[activity] <= time_index < start_times[activity] + instance.durations[activity]
            and instance.demands[activity][resource] > 0
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
        conflict.sort(key=lambda activity: (start_times[activity], activity))
        overload = [max(0, usage[resource_idx] - instance.capacities[resource_idx]) for resource_idx in range(instance.n_resources)]
        return time_index, resource, conflict, overload
    return None
