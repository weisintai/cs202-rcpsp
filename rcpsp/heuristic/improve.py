from __future__ import annotations

import random
import time

from ..config import HeuristicConfig, sample_heuristic_config
from ..core.compress import normalized_time_loads, resource_order_edges
from ..models import Edge, Instance, Schedule
from ..temporal import TemporalInfeasibleError, longest_feasible_starts
from ..validate import validate_schedule
from .construct import construct_schedule


def sample_removal_size(instance: Instance, rng: random.Random) -> int:
    minimum = 2 if instance.n_jobs <= 10 else 3
    maximum = max(minimum, min(instance.n_jobs - 1, max(3, instance.n_jobs // 3)))
    return rng.randint(minimum, maximum)


def mobility_removal_set(
    instance: Instance,
    schedule: Schedule,
    tail: list[int],
    rng: random.Random,
    size: int,
) -> set[int]:
    scored = []
    for activity in range(1, instance.sink):
        slack = schedule.makespan - (schedule.start_times[activity] + tail[activity])
        scored.append((slack, rng.random(), activity))
    scored.sort(reverse=True)
    pool = [activity for _, _, activity in scored[: max(size, min(len(scored), size * 2))]]
    if len(pool) <= size:
        return set(pool)
    return set(rng.sample(pool, size))


def non_peak_removal_set(
    instance: Instance,
    schedule: Schedule,
    rng: random.Random,
    size: int,
) -> set[int]:
    loads = normalized_time_loads(instance, schedule.start_times)
    scored = []
    for activity in range(1, instance.sink):
        start = schedule.start_times[activity]
        duration = instance.durations[activity]
        if duration == 0 or start >= len(loads):
            average_load = 0.0
        else:
            window = loads[start : start + duration]
            average_load = sum(window) / max(1, len(window))
        scored.append((average_load, rng.random(), activity))
    scored.sort()
    pool = [activity for _, _, activity in scored[: max(size, min(len(scored), size * 2))]]
    if len(pool) <= size:
        return set(pool)
    return set(rng.sample(pool, size))


def segment_removal_set(
    instance: Instance,
    schedule: Schedule,
    rng: random.Random,
    size: int,
) -> set[int]:
    if schedule.makespan <= 0:
        return mobility_removal_set(instance, schedule, [0] * instance.n_activities, rng, size)

    center = rng.randrange(max(1, schedule.makespan))
    half_width = max(1, schedule.makespan // max(6, instance.n_jobs))
    left = max(0, center - half_width)
    right = center + half_width + 1
    overlapping = [
        activity
        for activity in range(1, instance.sink)
        if schedule.start_times[activity] < right
        and schedule.start_times[activity] + instance.durations[activity] > left
    ]
    if len(overlapping) <= size:
        return set(overlapping)
    return set(rng.sample(overlapping, size))


def random_removal_set(instance: Instance, rng: random.Random, size: int) -> set[int]:
    activities = list(range(1, instance.sink))
    if len(activities) <= size:
        return set(activities)
    return set(rng.sample(activities, size))


def sample_removal_set(
    instance: Instance,
    schedule: Schedule,
    tail: list[int],
    rng: random.Random,
) -> set[int]:
    size = sample_removal_size(instance, rng)
    operator = rng.choice(("mobility", "non_peak", "segment", "random"))
    if operator == "mobility":
        removed = mobility_removal_set(instance, schedule, tail, rng, size)
    elif operator == "non_peak":
        removed = non_peak_removal_set(instance, schedule, rng, size)
    elif operator == "segment":
        removed = segment_removal_set(instance, schedule, rng, size)
    else:
        removed = random_removal_set(instance, rng, size)
    return removed or random_removal_set(instance, rng, min(size, instance.n_jobs))


def repair_schedule_subset(
    instance: Instance,
    schedule: Schedule,
    removed: set[int],
    tail: list[int],
    intensity: list[float],
    solver_config: HeuristicConfig,
    rng: random.Random,
    deadline: float,
) -> Schedule | None:
    base_edges = [
        edge
        for edge in resource_order_edges(instance, list(schedule.start_times))
        if edge.source not in removed and edge.target not in removed
    ]
    try:
        initial_starts = longest_feasible_starts(instance, extra_edges=base_edges)
    except TemporalInfeasibleError:
        return None

    candidate = construct_schedule(
        instance=instance,
        rng=rng,
        tail=tail,
        intensity=intensity,
        config=sample_heuristic_config(solver_config, rng),
        deadline=deadline,
        base_extra_edges=base_edges,
        initial_starts=initial_starts,
    )
    if validate_schedule(instance, candidate):
        return None
    return candidate


def update_elite_pool(elite: list[Schedule], candidate: Schedule, limit: int = 4) -> None:
    if any(existing.start_times == candidate.start_times for existing in elite):
        return
    elite.append(candidate)
    elite.sort(key=lambda schedule: (schedule.makespan, schedule.start_times))
    del elite[limit:]


def improve_incumbent(
    instance: Instance,
    incumbent: Schedule,
    tail: list[int],
    intensity: list[float],
    solver_config: HeuristicConfig,
    rng: random.Random,
    deadline: float,
) -> tuple[Schedule, int]:
    best = incumbent
    elite = [incumbent]
    iterations = 0
    stagnation = 0

    while time.perf_counter() < deadline:
        base = elite[0] if stagnation < 4 else rng.choice(elite[: min(len(elite), 3)])
        removed = sample_removal_set(instance, base, tail, rng)
        candidate = repair_schedule_subset(
            instance=instance,
            schedule=base,
            removed=removed,
            tail=tail,
            intensity=intensity,
            solver_config=solver_config,
            rng=rng,
            deadline=deadline,
        )
        iterations += 1
        if candidate is None:
            stagnation += 1
            continue

        update_elite_pool(elite, candidate)
        if candidate.makespan < best.makespan:
            best = candidate
            elite[0] = best
            elite.sort(key=lambda schedule: (schedule.makespan, schedule.start_times))
            stagnation = 0
        elif candidate.makespan < base.makespan:
            stagnation = max(0, stagnation - 1)
        else:
            stagnation += 1

    return best, iterations
