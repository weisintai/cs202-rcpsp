from __future__ import annotations

import random
import time
from dataclasses import dataclass

from ..config import HeuristicConfig, sample_heuristic_config
from ..core.compress import normalized_time_loads, resource_order_edges
from ..models import Edge, Instance, Schedule
from ..temporal import TemporalInfeasibleError, longest_feasible_starts
from ..validate import build_resource_profile, validate_schedule
from .construct import construct_schedule


@dataclass(frozen=True)
class RepairPlan:
    removed: frozenset[int]
    preferred_pairs: tuple[tuple[int, int], ...] = ()


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


def critical_chain_removal_set(
    instance: Instance,
    schedule: Schedule,
    tail: list[int],
    intensity: list[float],
    size: int,
) -> set[int]:
    scored = []
    for activity in range(1, instance.sink):
        slack = schedule.makespan - (schedule.start_times[activity] + tail[activity])
        scored.append((slack, -intensity[activity], schedule.start_times[activity], activity))
    scored.sort()
    return {activity for _, _, _, activity in scored[:size]}


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


def bottleneck_hotspot(instance: Instance, schedule: Schedule) -> tuple[int, int] | None:
    profile = build_resource_profile(instance, schedule.start_times)
    best: tuple[float, int, int, int] | None = None
    for time_index, usage in enumerate(profile):
        for resource, amount in enumerate(usage):
            capacity = instance.capacities[resource]
            if capacity <= 0 or amount <= 0:
                continue
            candidate = (amount / capacity, amount, -time_index, resource)
            if best is None or candidate > best:
                best = candidate
    if best is None:
        return None
    return best[3], -best[2]


def peak_focused_removal_set(
    instance: Instance,
    schedule: Schedule,
    tail: list[int],
    intensity: list[float],
    size: int,
) -> set[int]:
    hotspot = bottleneck_hotspot(instance, schedule)
    if hotspot is None:
        return critical_chain_removal_set(instance, schedule, tail, intensity, size)

    resource, time_index = hotspot
    half_width = max(1, schedule.makespan // max(8, instance.n_jobs))
    left = max(0, time_index - half_width)
    right = time_index + half_width + 1
    scored = []
    for activity in range(1, instance.sink):
        duration = instance.durations[activity]
        demand = instance.demands[activity][resource]
        if duration <= 0 or demand <= 0:
            continue
        start = schedule.start_times[activity]
        overlap = max(0, min(start + duration, right) - max(start, left))
        if overlap <= 0:
            continue
        slack = schedule.makespan - (start + tail[activity])
        scored.append(
            (
                overlap * demand,
                demand,
                -slack,
                intensity[activity],
                -start,
                activity,
            )
        )
    if not scored:
        return segment_removal_set(instance, schedule, random.Random(time_index + resource), size)
    scored.sort(reverse=True)
    return {activity for _, _, _, _, _, activity in scored[:size]}


def random_removal_set(instance: Instance, rng: random.Random, size: int) -> set[int]:
    activities = list(range(1, instance.sink))
    if len(activities) <= size:
        return set(activities)
    return set(rng.sample(activities, size))


def bottleneck_pair_repair_plans(
    instance: Instance,
    schedule: Schedule,
    tail: list[int],
    intensity: list[float],
    size: int,
) -> tuple[RepairPlan, ...]:
    hotspot = bottleneck_hotspot(instance, schedule)
    if hotspot is None:
        removed = critical_chain_removal_set(instance, schedule, tail, intensity, size)
        return (RepairPlan(frozenset(removed)),)

    resource, time_index = hotspot
    half_width = max(1, schedule.makespan // max(8, instance.n_jobs))
    left = max(0, time_index - half_width)
    right = time_index + half_width + 1
    relevant = [
        activity
        for activity in range(1, instance.sink)
        if instance.demands[activity][resource] > 0
        and max(0, min(schedule.start_times[activity] + instance.durations[activity], right) - max(schedule.start_times[activity], left)) > 0
    ]
    if len(relevant) < 2:
        removed = peak_focused_removal_set(instance, schedule, tail, intensity, size)
        return (RepairPlan(frozenset(removed)),)

    pair_candidates: list[tuple[tuple[float, ...], tuple[int, int]]] = []
    for index, first in enumerate(relevant):
        first_slack = schedule.makespan - (schedule.start_times[first] + tail[first])
        for second in relevant[index + 1 :]:
            second_slack = schedule.makespan - (schedule.start_times[second] + tail[second])
            pair_candidates.append(
                (
                    (
                        float(instance.demands[first][resource] + instance.demands[second][resource]),
                        intensity[first] + intensity[second],
                        -(first_slack + second_slack),
                        -abs(schedule.start_times[first] - schedule.start_times[second]),
                        -abs(first - second),
                    ),
                    (first, second),
                )
            )
    if not pair_candidates:
        removed = peak_focused_removal_set(instance, schedule, tail, intensity, size)
        return (RepairPlan(frozenset(removed)),)

    _, (first, second) = max(pair_candidates, key=lambda item: item[0])
    removed = {first, second}
    if len(removed) < size:
        extras: list[tuple[tuple[float, ...], int]] = []
        for activity in relevant:
            if activity in removed:
                continue
            slack = schedule.makespan - (schedule.start_times[activity] + tail[activity])
            start = schedule.start_times[activity]
            duration = instance.durations[activity]
            overlap = max(0, min(start + duration, right) - max(start, left))
            extras.append(
                (
                    (
                        float(overlap * instance.demands[activity][resource]),
                        intensity[activity],
                        -slack,
                        -abs(start - time_index),
                    ),
                    activity,
                )
            )
        extras.sort(reverse=True)
        for _, activity in extras:
            removed.add(activity)
            if len(removed) >= size:
                break

    current_pair = (first, second)
    if schedule.start_times[second] < schedule.start_times[first]:
        current_pair = (second, first)
    swapped_pair = (current_pair[1], current_pair[0])
    plans = [RepairPlan(frozenset(removed))]
    plans.append(RepairPlan(frozenset(removed), (current_pair,)))
    if swapped_pair != current_pair:
        plans.append(RepairPlan(frozenset(removed), (swapped_pair,)))
    return tuple(plans)


def sample_standard_repair_plan(
    instance: Instance,
    schedule: Schedule,
    tail: list[int],
    rng: random.Random,
) -> RepairPlan:
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
    fallback = removed or random_removal_set(instance, rng, min(size, instance.n_jobs))
    return RepairPlan(frozenset(fallback))


def sample_repair_plans(
    instance: Instance,
    schedule: Schedule,
    tail: list[int],
    intensity: list[float],
    rng: random.Random,
) -> tuple[RepairPlan, ...]:
    if instance.n_jobs < 30:
        return (sample_standard_repair_plan(instance, schedule, tail, rng),)

    size = sample_removal_size(instance, rng)
    operator = rng.choice(
        (
            "critical_chain",
            "peak",
            "pair",
            "mobility",
            "non_peak",
            "segment",
            "random",
        )
    )
    if operator == "critical_chain":
        removed = critical_chain_removal_set(instance, schedule, tail, intensity, size)
        return (RepairPlan(frozenset(removed)),)
    if operator == "peak":
        removed = peak_focused_removal_set(instance, schedule, tail, intensity, size)
        return (RepairPlan(frozenset(removed)),)
    if operator == "pair":
        return bottleneck_pair_repair_plans(instance, schedule, tail, intensity, size)
    if operator == "mobility":
        removed = mobility_removal_set(instance, schedule, tail, rng, size)
    elif operator == "non_peak":
        removed = non_peak_removal_set(instance, schedule, rng, size)
    elif operator == "segment":
        removed = segment_removal_set(instance, schedule, rng, size)
    else:
        removed = random_removal_set(instance, rng, size)
    fallback = removed or random_removal_set(instance, rng, min(size, instance.n_jobs))
    return (RepairPlan(frozenset(fallback)),)


def repair_schedule_subset(
    instance: Instance,
    schedule: Schedule,
    removed: set[int],
    tail: list[int],
    intensity: list[float],
    solver_config: HeuristicConfig,
    rng: random.Random,
    deadline: float,
    preferred_pairs: tuple[tuple[int, int], ...] = (),
) -> Schedule | None:
    base_edges = [
        edge
        for edge in resource_order_edges(instance, list(schedule.start_times))
        if edge.source not in removed and edge.target not in removed
    ]
    seen_pairs = {(edge.source, edge.target) for edge in base_edges}
    for source, target in preferred_pairs:
        if source == target or (source, target) in seen_pairs:
            continue
        base_edges.append(Edge(source=source, target=target, lag=instance.durations[source]))
        seen_pairs.add((source, target))
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


def select_improvement_bases(
    elite: list[Schedule],
    rng: random.Random,
    stagnation: int,
    targeted_mode: bool,
) -> list[Schedule]:
    if not elite:
        return []
    if not targeted_mode:
        return [elite[0]]
    bases = [elite[0]]
    pool = elite[1 : min(len(elite), 2 + stagnation // 3)]
    while pool and len(bases) < 1 + min(2, stagnation // 4):
        selected = rng.choice(pool)
        bases.append(selected)
        pool = [candidate for candidate in pool if candidate.start_times != selected.start_times]
    return bases


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
    targeted_mode = instance.n_jobs >= 30
    elite_limit = 6 if targeted_mode else 4

    while time.perf_counter() < deadline:
        attempts: list[tuple[Schedule, Schedule]] = []
        bases = select_improvement_bases(elite, rng, stagnation, targeted_mode)
        for base in bases:
            if time.perf_counter() >= deadline:
                break
            plans = sample_repair_plans(instance, base, tail, intensity, rng)
            for plan in plans:
                if time.perf_counter() >= deadline:
                    break
                candidate = repair_schedule_subset(
                    instance=instance,
                    schedule=base,
                    removed=set(plan.removed),
                    tail=tail,
                    intensity=intensity,
                    solver_config=solver_config,
                    rng=rng,
                    deadline=deadline,
                    preferred_pairs=plan.preferred_pairs,
                )
                iterations += 1
                if candidate is None:
                    continue
                update_elite_pool(elite, candidate, limit=elite_limit)
                attempts.append((candidate, base))

        if not attempts:
            stagnation += max(1, len(bases))
            continue

        candidate, base = min(
            attempts,
            key=lambda item: (item[0].makespan, item[0].start_times),
        )
        if candidate.makespan < best.makespan:
            best = candidate
            update_elite_pool(elite, best, limit=elite_limit)
            stagnation = 0
        elif any(attempt.makespan < origin.makespan for attempt, origin in attempts):
            stagnation = max(0, stagnation - 1)
        else:
            stagnation += 1

    return best, iterations
