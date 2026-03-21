from __future__ import annotations

import random

from ..models import Schedule
from .graph import random_topological_order
from .models import SgsInstance
from .time_windows import POS_INF, window_slack

NEG_INF = float("-inf")


def _tail_to_sink(instance: SgsInstance, activity: int) -> int:
    tail = instance.lag_dist[activity][instance.sink]
    return 0 if tail == NEG_INF else int(tail)


def _resource_pressure(instance: SgsInstance, activity: int) -> float:
    descriptor = instance.activities[activity]
    pressure = 0.0
    for resource, demand in enumerate(descriptor.demands):
        capacity = instance.capacities[resource]
        if capacity > 0:
            pressure += demand / capacity
    return pressure


def _critical_slack(
    instance: SgsInstance,
    temporal_lower: list[int],
    activity: int,
) -> int:
    project_lower = temporal_lower[instance.sink]
    return project_lower - (temporal_lower[activity] + _tail_to_sink(instance, activity))


def _priority_slack(
    instance: SgsInstance,
    temporal_lower: list[int],
    activity: int,
    latest_starts: list[int] | None,
) -> int:
    if latest_starts is None:
        return _critical_slack(instance, temporal_lower, activity)
    return window_slack(temporal_lower[activity], latest_starts[activity])


def _priority_window_slack(
    temporal_lower: list[int],
    activity: int,
    latest_starts: list[int] | None,
) -> int:
    if latest_starts is None:
        return POS_INF
    return window_slack(temporal_lower[activity], latest_starts[activity])


def _append_unique(
    priorities: list[tuple[int, ...]],
    candidate: tuple[int, ...],
) -> None:
    if candidate not in priorities:
        priorities.append(candidate)


def _all_predecessors(instance: SgsInstance) -> dict[int, set[int]]:
    all_pred = {activity: set() for activity in instance.internal_activities}
    for activity in instance.topo_order:
        if activity not in all_pred:
            continue
        for predecessor in instance.activities[activity].min_predecessors:
            if predecessor.activity in all_pred:
                all_pred[activity] |= all_pred[predecessor.activity] | {predecessor.activity}
    return all_pred


def _all_successors(instance: SgsInstance) -> dict[int, set[int]]:
    all_succ = {activity: set() for activity in instance.internal_activities}
    for activity in reversed(instance.topo_order):
        if activity not in all_succ:
            continue
        for successor in instance.activities[activity].min_successors:
            if successor.activity in all_succ:
                all_succ[activity] |= all_succ[successor.activity] | {successor.activity}
    return all_succ


def _reinsert_jobs(
    instance: SgsInstance,
    order: list[int],
    removed: list[int],
    rng: random.Random,
) -> tuple[int, ...]:
    all_pred = _all_predecessors(instance)
    all_succ = _all_successors(instance)
    remaining = order[:]

    for job in removed:
        indices = {activity: idx for idx, activity in enumerate(remaining)}
        left_limit = max((indices[pred] for pred in all_pred[job] if pred in indices), default=-1) + 1
        right_limit = min((indices[succ] for succ in all_succ[job] if succ in indices), default=len(remaining))
        insert_at = left_limit if left_limit >= right_limit else rng.randrange(left_limit, right_limit)
        remaining.insert(insert_at, job)

    return tuple(remaining)


def _topological_order_by_key(
    instance: SgsInstance,
    key_fn,
) -> tuple[int, ...]:
    remaining = {activity: 0 for activity in instance.internal_activities}
    successors: dict[int, list[int]] = {activity: [] for activity in instance.internal_activities}

    for activity in instance.internal_activities:
        for predecessor in instance.activities[activity].min_predecessors:
            if predecessor.activity in remaining:
                remaining[activity] += 1
        for successor in instance.activities[activity].min_successors:
            if successor.activity in remaining:
                successors[activity].append(successor.activity)

    ready = [activity for activity in instance.internal_activities if remaining[activity] == 0]
    order: list[int] = []

    while ready:
        selected = min(ready, key=key_fn)
        ready.remove(selected)
        order.append(selected)
        for successor in successors[selected]:
            remaining[successor] -= 1
            if remaining[successor] == 0:
                ready.append(successor)

    if len(order) != len(instance.internal_activities):
        return instance.internal_activities
    return tuple(order)


def priority_from_schedule(
    instance: SgsInstance,
    schedule: Schedule,
) -> tuple[int, ...]:
    return _topological_order_by_key(
        instance,
        key_fn=lambda activity: (
            schedule.start_times[activity],
            schedule.start_times[activity] + instance.activities[activity].duration,
            activity,
        ),
    )


def reverse_priority_from_schedule(
    instance: SgsInstance,
    schedule: Schedule,
) -> tuple[int, ...]:
    return _topological_order_by_key(
        instance,
        key_fn=lambda activity: (
            -(schedule.start_times[activity] + instance.activities[activity].duration),
            -schedule.start_times[activity],
            activity,
        ),
    )


def seed_priority_lists(
    instance: SgsInstance,
    temporal_lower: list[int],
    latest_starts: list[int] | None = None,
) -> list[tuple[int, ...]]:
    priorities: list[tuple[int, ...]] = []

    _append_unique(priorities, instance.internal_activities)
    _append_unique(
        priorities,
        _topological_order_by_key(
            instance,
            key_fn=lambda activity: (
                temporal_lower[activity],
                temporal_lower[activity] + instance.activities[activity].duration,
                activity,
            ),
        ),
    )
    _append_unique(
        priorities,
        _topological_order_by_key(
            instance,
            key_fn=lambda activity: (
                _critical_slack(instance, temporal_lower, activity),
                _priority_window_slack(temporal_lower, activity, latest_starts),
                -_tail_to_sink(instance, activity),
                temporal_lower[activity],
                activity,
            ),
        ),
    )
    _append_unique(
        priorities,
        _topological_order_by_key(
            instance,
            key_fn=lambda activity: (
                -_resource_pressure(instance, activity),
                _critical_slack(instance, temporal_lower, activity),
                _priority_window_slack(temporal_lower, activity, latest_starts),
                temporal_lower[activity],
                activity,
            ),
        ),
    )
    _append_unique(
        priorities,
        _topological_order_by_key(
            instance,
            key_fn=lambda activity: (
                -_tail_to_sink(instance, activity),
                -len(instance.activities[activity].max_successors),
                -len(instance.activities[activity].max_predecessors),
                temporal_lower[activity],
                activity,
            ),
        ),
    )
    return priorities


def sample_priority_order(
    instance: SgsInstance,
    temporal_lower: list[int],
    rng: random.Random,
    latest_starts: list[int] | None = None,
) -> tuple[int, ...]:
    return _topological_order_by_key(
        instance,
        key_fn=lambda activity: (
            _critical_slack(instance, temporal_lower, activity) + rng.uniform(-2.5, 2.5),
            _priority_window_slack(temporal_lower, activity, latest_starts) + rng.uniform(-1.5, 1.5),
            -(_tail_to_sink(instance, activity) + rng.uniform(-3.0, 3.0)),
            -(_resource_pressure(instance, activity) + rng.uniform(-0.15, 0.15)),
            -(4.0 * len(instance.activities[activity].max_successors) + rng.uniform(-1.0, 1.0)),
            temporal_lower[activity] + rng.uniform(-2.0, 2.0),
            rng.random(),
            activity,
        ),
    )


def perturb_priority_order(
    instance: SgsInstance,
    temporal_lower: list[int],
    base_priority: tuple[int, ...] | list[int],
    rng: random.Random,
) -> tuple[int, ...]:
    order = [activity for activity in base_priority if activity in instance.internal_activities]
    if len(order) <= 2:
        return tuple(order)

    remove_count = max(1, min(4, len(order) // 5))
    remove_index_set = set(rng.sample(range(len(order)), remove_count))
    removed = [activity for index, activity in enumerate(order) if index in remove_index_set]
    remaining = [activity for index, activity in enumerate(order) if index not in remove_index_set]
    return _reinsert_jobs(instance, remaining, removed, rng)


def repair_priority_order(
    instance: SgsInstance,
    partial_priority: tuple[int, ...] | list[int],
    rng: random.Random,
) -> tuple[int, ...]:
    order = [activity for activity in partial_priority if activity in instance.internal_activities]
    present = set(order)
    missing = [activity for activity in instance.internal_activities if activity not in present]
    return _reinsert_jobs(instance, order, missing, rng)


def segment_perturb_priority_order(
    instance: SgsInstance,
    base_priority: tuple[int, ...] | list[int],
    rng: random.Random,
) -> tuple[int, ...]:
    order = [activity for activity in base_priority if activity in instance.internal_activities]
    if len(order) <= 3:
        return tuple(order)

    segment_size = max(1, min(5, len(order) // 4))
    start = rng.randrange(0, max(1, len(order) - segment_size + 1))
    stop = min(len(order), start + segment_size)
    removed = order[start:stop]
    remaining = order[:start] + order[stop:]
    rng.shuffle(removed)
    return _reinsert_jobs(instance, remaining, removed, rng)


def incumbent_neighbor_priority_order(
    instance: SgsInstance,
    temporal_lower: list[int],
    current_priority: tuple[int, ...] | list[int],
    best_priority: tuple[int, ...] | list[int] | None,
    rng: random.Random,
    iteration: int,
    latest_starts: list[int] | None = None,
) -> tuple[int, ...]:
    phase = iteration % 4
    if phase == 0:
        return perturb_priority_order(instance, temporal_lower, current_priority, rng)
    if phase == 1:
        return segment_perturb_priority_order(instance, current_priority, rng)
    if phase == 2 and best_priority is not None:
        return perturb_priority_order(instance, temporal_lower, best_priority, rng)

    return sample_priority_order(instance, temporal_lower, rng, latest_starts)


def priority_order_for_restart(
    instance: SgsInstance,
    temporal_lower: list[int],
    rng: random.Random,
    restart: int,
    seeded_priorities: list[tuple[int, ...]] | tuple[tuple[int, ...], ...],
    incumbent_priority: tuple[int, ...] | None = None,
    latest_starts: list[int] | None = None,
) -> tuple[int, ...]:
    if restart < len(seeded_priorities):
        return seeded_priorities[restart]

    offset = restart - len(seeded_priorities)
    phase = offset % 3
    if phase == 0:
        return tuple(
            activity
            for activity in random_topological_order(instance, rng)
            if activity not in (instance.source, instance.sink)
        )
    if phase == 1:
        return sample_priority_order(instance, temporal_lower, rng, latest_starts)

    base_priority = incumbent_priority or seeded_priorities[offset % len(seeded_priorities)]
    return perturb_priority_order(instance, temporal_lower, base_priority, rng)
