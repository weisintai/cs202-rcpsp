from __future__ import annotations

import random

from ..models import Schedule
from .graph import random_topological_order
from .models import SgsInstance

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


def _append_unique(
    priorities: list[tuple[int, ...]],
    candidate: tuple[int, ...],
) -> None:
    if candidate not in priorities:
        priorities.append(candidate)


def priority_from_schedule(
    instance: SgsInstance,
    schedule: Schedule,
) -> tuple[int, ...]:
    return tuple(
        sorted(
            instance.internal_activities,
            key=lambda activity: (
                schedule.start_times[activity],
                schedule.start_times[activity] + instance.activities[activity].duration,
                activity,
            ),
        )
    )


def reverse_priority_from_schedule(
    instance: SgsInstance,
    schedule: Schedule,
) -> tuple[int, ...]:
    return tuple(
        sorted(
            instance.internal_activities,
            key=lambda activity: (
                -(schedule.start_times[activity] + instance.activities[activity].duration),
                -schedule.start_times[activity],
                activity,
            ),
        )
    )


def seed_priority_lists(
    instance: SgsInstance,
    temporal_lower: list[int],
) -> list[tuple[int, ...]]:
    priorities: list[tuple[int, ...]] = []

    _append_unique(priorities, instance.internal_activities)
    _append_unique(
        priorities,
        tuple(
            sorted(
                instance.internal_activities,
                key=lambda activity: (
                    temporal_lower[activity],
                    temporal_lower[activity] + instance.activities[activity].duration,
                    activity,
                ),
            )
        ),
    )
    _append_unique(
        priorities,
        tuple(
            sorted(
                instance.internal_activities,
                key=lambda activity: (
                    _critical_slack(instance, temporal_lower, activity),
                    -_tail_to_sink(instance, activity),
                    temporal_lower[activity],
                    activity,
                ),
            )
        ),
    )
    _append_unique(
        priorities,
        tuple(
            sorted(
                instance.internal_activities,
                key=lambda activity: (
                    -_resource_pressure(instance, activity),
                    _critical_slack(instance, temporal_lower, activity),
                    temporal_lower[activity],
                    activity,
                ),
            )
        ),
    )
    _append_unique(
        priorities,
        tuple(
            sorted(
                instance.internal_activities,
                key=lambda activity: (
                    -_tail_to_sink(instance, activity),
                    -len(instance.activities[activity].max_successors),
                    -len(instance.activities[activity].max_predecessors),
                    temporal_lower[activity],
                    activity,
                ),
            )
        ),
    )
    return priorities


def sample_priority_order(
    instance: SgsInstance,
    temporal_lower: list[int],
    rng: random.Random,
) -> tuple[int, ...]:
    ranked = []
    for activity in instance.internal_activities:
        tail_score = _tail_to_sink(instance, activity)
        descriptor = instance.activities[activity]
        ranked.append(
            (
                _critical_slack(instance, temporal_lower, activity) + rng.uniform(-2.5, 2.5),
                -(tail_score + rng.uniform(-3.0, 3.0)),
                -(_resource_pressure(instance, activity) + rng.uniform(-0.15, 0.15)),
                -(4.0 * len(descriptor.max_successors) + rng.uniform(-1.0, 1.0)),
                temporal_lower[activity] + rng.uniform(-2.0, 2.0),
                rng.random(),
                activity,
            )
        )

    ranked.sort()
    return tuple(activity for *_, activity in ranked)


def perturb_priority_order(
    instance: SgsInstance,
    temporal_lower: list[int],
    base_priority: tuple[int, ...] | list[int],
    rng: random.Random,
) -> tuple[int, ...]:
    base_rank = {activity: index for index, activity in enumerate(base_priority)}
    ranked = []
    for activity in instance.internal_activities:
        ranked.append(
            (
                base_rank.get(activity, len(base_priority)) + rng.uniform(-2.0, 2.0),
                _critical_slack(instance, temporal_lower, activity) + rng.uniform(-1.0, 1.0),
                -(_resource_pressure(instance, activity) + rng.uniform(-0.1, 0.1)),
                rng.random(),
                activity,
            )
        )
    ranked.sort()
    return tuple(activity for *_, activity in ranked)


def priority_order_for_restart(
    instance: SgsInstance,
    temporal_lower: list[int],
    rng: random.Random,
    restart: int,
    seeded_priorities: list[tuple[int, ...]] | tuple[tuple[int, ...], ...],
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
        return sample_priority_order(instance, temporal_lower, rng)

    base_priority = seeded_priorities[offset % len(seeded_priorities)]
    return perturb_priority_order(instance, temporal_lower, base_priority, rng)
