from __future__ import annotations

from ..models import Instance
from ..validate import build_resource_profile

BranchConflict = tuple[int, int, tuple[int, ...], tuple[int, ...]]


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
        active.sort(key=lambda activity: (instance.demands[activity][resource], instance.durations[activity], activity))
        total = sum(instance.demands[activity][resource] for activity in active)
        index = 0
        while index < len(active):
            if total - instance.demands[active[index]][resource] > instance.capacities[resource]:
                total -= instance.demands[active[index]][resource]
                index += 1
            else:
                break
        conflict = active[index:]
        conflict.sort(key=lambda activity: (start_times[activity], activity))
        overload = [max(0, usage[resource_idx] - instance.capacities[resource_idx]) for resource_idx in range(instance.n_resources)]
        return time_index, resource, conflict, overload
    return None


def select_branch_conflict(
    instance: Instance,
    start_times: list[int] | tuple[int, ...],
    latest: tuple[int, ...] | None,
) -> BranchConflict | None:
    profile = build_resource_profile(instance, start_times)
    best: tuple[tuple[int, int, int, int, int], BranchConflict] | None = None

    for time_index, usage in enumerate(profile):
        overloaded = [resource for resource in range(instance.n_resources) if usage[resource] > instance.capacities[resource]]
        if not overloaded:
            continue

        all_active_here = [
            activity
            for activity in range(1, instance.sink)
            if start_times[activity] <= time_index < start_times[activity] + instance.durations[activity]
        ]
        overload = tuple(
            max(0, usage[resource_idx] - instance.capacities[resource_idx])
            for resource_idx in range(instance.n_resources)
        )

        for resource in overloaded:
            active = [activity for activity in all_active_here if instance.demands[activity][resource] > 0]
            active.sort(key=lambda activity: (instance.demands[activity][resource], instance.durations[activity], activity))
            total = sum(instance.demands[activity][resource] for activity in active)
            index = 0
            while index < len(active):
                if total - instance.demands[active[index]][resource] > instance.capacities[resource]:
                    total -= instance.demands[active[index]][resource]
                    index += 1
                else:
                    break
            conflict = tuple(sorted(active[index:], key=lambda activity: (start_times[activity], activity)))
            if len(conflict) <= 1:
                continue

            total_slack = 0
            if latest is not None:
                total_slack = sum(max(0, latest[activity] - start_times[activity]) for activity in conflict)

            key = (
                len(conflict),
                total_slack,
                -overload[resource],
                time_index,
                -sum(instance.demands[activity][resource] for activity in conflict),
            )
            candidate: BranchConflict = (time_index, resource, conflict, overload)
            if best is None or key < best[0]:
                best = (key, candidate)

    if best is None:
        return None
    return best[1]
